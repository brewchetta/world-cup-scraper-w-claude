# World Cup Scraper

Headless scraper for **FIFA World Cup player statistics** (name, jersey number, goals,
minutes played, fouls) for tournaments from **1970 to present**, loaded into a
**Supabase / Postgres** database. A REST API will be layered on later.

The scraper reads data by **scraping the rendered web pages directly** with Playwright
(navigate → let JavaScript render → parse the DOM). It does **not** use any JSON API or
data feed — this is intentional, as a real web-scraping exercise.

Source: ESPN soccer pages (league slug `fifa.world`).

## Data model (per-match grain)

One row per player per match in `player_match_stats`; all stat fields are nullable because
older tournaments lack fouls/minutes. Tournament and career totals are SQL **views** over the
per-match table, so the future API queries aggregates without duplicating storage. See
[`src/wc_scraper/db/schema.sql`](src/wc_scraper/db/schema.sql) and the DBML mirror
[`schema.dbml`](src/wc_scraper/db/schema.dbml).

## Setup

```bash
python -m venv .venv
. .venv/Scripts/activate     # Windows; on POSIX: source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env         # then edit values
```

### Supabase / Postgres

1. Create a project at https://supabase.com.
2. Project Settings → Database → Connection string → **Session pooler**. Copy it into
   `.env` as `DATABASE_URL` (the session/direct connection is required to run DDL).
3. Create the schema:
   ```bash
   wc-scrape initdb
   # or: psql "$DATABASE_URL" -f src/wc_scraper/db/schema.sql
   ```

You can develop against a **local** Postgres first (e.g.
`docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres`) and just change
`DATABASE_URL` to point at Supabase later — the schema and loader are identical.

## Usage

```bash
wc-scrape initdb                       # create tables + views
wc-scrape run --year 2010              # scrape one tournament and load it
wc-scrape run --game 264123 --no-load  # scrape a single match, print, don't load
wc-scrape run --all                    # all tournaments 1970..present
```

Add `--no-headless` to watch the browser while debugging. Rendered HTML is cached under
`WC_CACHE_DIR` (default `.cache/`) so re-runs and parser tweaks don't re-hit ESPN.

## API server

A FastAPI read API lives in `src/wc_scraper/api/` (decoupled from the scraper).

```bash
pip install -e ".[api]"
# set BOOTSTRAP_ADMIN_KEY in .env, then:
wc-api serve                       # http://127.0.0.1:8000  (Swagger at /docs)
```

- **Guests** can read all `GET` endpoints. **Writes/admin require an API key** sent as
  `Authorization: Bearer <key>`.
- **Rate limiting** is tiered and in-memory: guests by IP (`WC_API_GUEST_RPM`), key-holders
  by key (`WC_API_CLIENT_RPM`).
- **Keys** are SHA-256-hashed at rest; the plaintext is shown once. Manage them via the CLI
  (direct DB) or the admin HTTP routes:
  ```bash
  wc-api create-key "Acme Corp"      # or --admin
  wc-api rotate-key 3                 # new secret, old one dies immediately
  wc-api revoke-key 3
  wc-api list-keys
  ```
  The first admin key is bootstrapped via `BOOTSTRAP_ADMIN_KEY` (recognized as an admin
  credential), which can then mint others through `POST /admin/keys`.

Read endpoints: `/tournaments`, `/tournaments/{year}`, `/tournaments/{year}/top-scorers`,
`/teams`, `/players` (`?name=`), `/players/{id}`, `/players/{id}/totals`, `/matches`
(`?year=`), `/matches/{id}`. Auth: `/me` (verify a key), admin: `/admin/keys`.

> Write endpoints are intentionally not built yet (read-only first). The auth plumbing
> (`require_client`) is in place so adding them later is straightforward.

## Data coverage & limitations

This was validated against real ESPN pages. What the **visible DOM** actually yields:

| Era | What renders | Fields we extract |
|-----|--------------|-------------------|
| 2014–present | Full squads (~26/team) in a "Formations & Lineups" section | name, ESPN athlete id, jersey number, team |
| 2010 and earlier | Only a 6-player "key matchups" widget (no full XI exists on the page) | name, athlete id, goals; jersey/team best-effort |

Honest caveats, by design (all stat columns are nullable):

- **Minutes played** and **fouls** are not reliably present per-player in the visible DOM, so
  they are usually `NULL`. The schema and loader already support them for when a future
  parser (or a richer page) provides them.
- **Goals** are parsed only from the old matchup widget today; for 2014+ full lineups, goals
  render as on-pitch icons and are left `NULL` for now.
- Player names come from the profile-link slug, so **diacritics are lost** (e.g. "Munoz").
  The stable `espn_athlete_id` is the real identity key.
- Discovery walks the **scoreboard day-by-day** across each tournament's date window
  (`TOURNAMENT_WINDOWS` in `config.py`), because ESPN's `/schedule/season/{year}` URL
  ignores the year. Years ESPN doesn't cover simply yield zero matches.

## Tests

```bash
pytest
```

Parser tests run against saved HTML fixtures in `tests/fixtures/` — no network required.

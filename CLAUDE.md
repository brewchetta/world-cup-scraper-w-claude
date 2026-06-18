# CLAUDE.md

Guidance for working in this repo.

## What this is

A headless scraper that collects **FIFA World Cup player stats** (name, jersey number,
goals, minutes, fouls) from **ESPN** and loads them into **Supabase/Postgres**, per-match
grained. A REST API is a later phase.

## Non-negotiable principle

**Scrape the rendered, human-visible DOM only.** Do NOT call ESPN's JSON APIs or parse the
page's embedded `__espnfitt__` state blob — this is a deliberate web-scraping exercise.
Playwright renders the page; we read `page.content()` and parse it with BeautifulSoup.

## Architecture (`src/wc_scraper/`)

- `config.py` — env settings + `TOURNAMENT_WINDOWS` (per-tournament date ranges, 1970–2026).
- `espn_client.py` — one headless Chromium context; navigate → scroll to lazy-load → return
  HTML; disk-caches pages under `.cache/` (won't cache undersized failed renders).
- `discovery.py` — extract gameIds from a rendered scoreboard page.
- `parsers.py` — pure HTML→records functions; handles both ESPN layouts; defensive (missing
  element → `None`, never raises).
- `pipeline.py` — discover (scoreboard day-by-day) → fetch → parse → load.
- `db/loader.py` — idempotent psycopg upserts; `db/schema.sql` is the source of truth (DDL),
  `db/schema.dbml` mirrors it for diagrams.
- `cli.py` — `wc-scrape initdb` and `wc-scrape run` (typer).

## Commands

```bash
pip install -e ".[dev]" && playwright install chromium   # setup
pytest                                                    # parser tests (no network)
wc-scrape initdb                                          # create tables + views
wc-scrape run --year 2022                                 # scrape + load a tournament
wc-scrape run --game <id> --year <yr> --no-load           # one match, print only
```

Tests run against saved HTML in `tests/fixtures/`; regenerate with
`python scripts/capture_fixtures.py` (network required).

## Hard-won facts (don't relearn these)

- ESPN `/schedule/season/{year}` **ignores the year** — discover via scoreboard-by-date.
- Full per-player lineups render only for **~2014+**; 2010 and earlier expose just a
  6-player "key matchups" widget. The parser handles both; all stat columns are nullable.
- Lineup pages use **randomized CSS class names** — never select on them. Anchor on the
  player-profile `href` (`/soccer/player/_/id/{athleteId}/{slug}`); jersey is the *first*
  number after the name (`Munoz|2|1` → 2). Scoreboard pages DO have stable classes
  (`Scoreboard`, `HeaderScoreboard`); drop `HeaderScoreboard` to avoid leaking other-year games.
- Player identity = `espn_athlete_id`; the name/dob unique index is **partial**
  (`WHERE espn_athlete_id IS NULL`) because distinct people share names.
- Names come from the URL slug, so **diacritics are lost**.
- `minutes_played` and `fouls_committed` are usually `NULL` (not in the visible DOM);
  `goals` is parsed only from the old widget so far.

## Database

Secrets live in `.env` (gitignored). Supabase's **direct** `db.<ref>.supabase.co` host is
IPv6-only and unreachable from IPv4 networks — use the **Session pooler** string
(`...pooler.supabase.com:5432`, user `postgres.<ref>`).

## Conventions

- Keep parsers pure and defensive; add a fixture + test when changing parsing behavior.
- The loader must stay idempotent (re-running a tournament must not duplicate rows).
- Never commit `.env`, `.cache/`, or `.venv/`.

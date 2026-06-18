"""Orchestration: discover -> fetch rendered HTML -> parse -> load."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import psycopg

from . import discovery, parsers
from .config import TOURNAMENT_WINDOWS
from .espn_client import ESPNBrowser, lineups_url, scoreboard_url
from .models import MatchScrape

# Men's World Cup years we attempt, 1970 -> present.
TOURNAMENT_YEARS = sorted(TOURNAMENT_WINDOWS)

# Selectors we wait on so we know the JS-rendered content has arrived.
_SCOREBOARD_WAIT = "a[href*='/gameId/']"
_LINEUPS_WAIT = "a[href*='/soccer/player/']"


def _dates_in_window(year: int):
    start_s, end_s = TOURNAMENT_WINDOWS[year]
    start, end = date.fromisoformat(start_s), date.fromisoformat(end_s)
    d = start
    while d <= end:
        yield d.strftime("%Y%m%d")
        d += timedelta(days=1)


def discover_game_ids(browser: ESPNBrowser, year: int) -> list[str]:
    """Walk the scoreboard day-by-day across the tournament window, collecting gameIds."""
    seen: dict[str, None] = {}
    for ymd in _dates_in_window(year):
        try:
            html = browser.fetch(scoreboard_url(ymd), wait_selector=_SCOREBOARD_WAIT)
        except Exception as exc:
            print(f"[{year}] scoreboard {ymd}: FAILED ({exc})")
            continue
        for gid in discovery.parse_schedule(html):
            seen.setdefault(gid, None)
    return list(seen.keys())


def scrape_match(browser: ESPNBrowser, game_id: str, year: int) -> MatchScrape:
    l_url = lineups_url(game_id)
    lineups_html = browser.fetch(l_url, wait_selector=_LINEUPS_WAIT)
    # matchstats is fetched lazily only if a future parser needs team-level stats.
    return parsers.parse_match(
        game_id=game_id,
        year=year,
        lineups_html=lineups_html,
        matchstats_html="",
        lineups_url=l_url,
    )


def run_year(
    browser: ESPNBrowser,
    year: int,
    conn: Optional[psycopg.Connection] = None,
) -> list[MatchScrape]:
    results: list[MatchScrape] = []
    game_ids = discover_game_ids(browser, year)
    print(f"[{year}] discovered {len(game_ids)} matches")
    for gid in game_ids:
        try:
            scrape = scrape_match(browser, gid, year)
        except Exception as exc:  # one bad match shouldn't kill the run
            print(f"[{year}] gameId {gid}: FAILED ({exc})")
            continue
        results.append(scrape)
        if conn is not None:
            from .db import loader

            loader.load_match(conn, scrape)
        print(f"[{year}] gameId {gid}: {len(scrape.stats)} player rows")
    return results

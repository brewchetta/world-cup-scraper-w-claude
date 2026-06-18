"""Orchestration: discover -> fetch rendered HTML -> parse -> load."""

from __future__ import annotations

from datetime import date, datetime, timedelta
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


def _process_game(
    browser: ESPNBrowser,
    game_id: str,
    year: int,
    conn: Optional[psycopg.Connection],
    results: list[MatchScrape],
) -> None:
    """Scrape one match and (optionally) load it; one failure never aborts the run."""
    try:
        scrape = scrape_match(browser, game_id, year)
    except Exception as exc:
        print(f"[{year}] gameId {game_id}: FAILED ({exc})")
        return
    # Not-yet-played matches render no score/teams in the title; skip them so a live run
    # doesn't create junk "Unknown" rows. They'll load once the match has data.
    if scrape.match.home_team == "Unknown" or scrape.match.away_team == "Unknown":
        print(f"[{year}] gameId {game_id}: skipped (no match data yet)")
        return
    results.append(scrape)
    if conn is not None:
        from .db import loader

        loader.load_match(conn, scrape)
    print(f"[{year}] gameId {game_id}: {len(scrape.stats)} player rows")


def _discover_dates(browser: ESPNBrowser, ymds: list[str]) -> dict[str, int]:
    """Map each discovered gameId -> its tournament year, across the given dates."""
    gid_year: dict[str, int] = {}
    for ymd in ymds:
        year = int(ymd[:4])
        try:
            html = browser.fetch(scoreboard_url(ymd), wait_selector=_SCOREBOARD_WAIT)
        except Exception as exc:
            print(f"scoreboard {ymd}: FAILED ({exc})")
            continue
        ids = discovery.parse_schedule(html)
        print(f"[{ymd}] {len(ids)} matches")
        for gid in ids:
            gid_year.setdefault(gid, year)
    return gid_year


def run_year(
    browser: ESPNBrowser,
    year: int,
    conn: Optional[psycopg.Connection] = None,
) -> list[MatchScrape]:
    """Scrape and load an entire tournament (walks its full date window)."""
    results: list[MatchScrape] = []
    gid_year = _discover_dates(browser, list(_dates_in_window(year)))
    print(f"[{year}] discovered {len(gid_year)} matches")
    for gid in gid_year:
        _process_game(browser, gid, year, conn, results)
    return results


def run_recent(
    browser: ESPNBrowser,
    days: int = 1,
    conn: Optional[psycopg.Connection] = None,
    today: Optional[date] = None,
) -> list[MatchScrape]:
    """Scrape only the current tournament's recent dates (today and `days` prior days).

    Designed for a cheap, frequent (e.g. hourly) live-update job. Pair with a fresh
    (cache-bypassing) browser so in-progress scores/lineups actually refresh.
    """
    today = today or datetime.now().date()
    candidates = sorted(today - timedelta(days=i) for i in range(days + 1))

    # Keep only dates that fall inside a known World Cup window.
    windows = {
        yr: (date.fromisoformat(s), date.fromisoformat(e))
        for yr, (s, e) in TOURNAMENT_WINDOWS.items()
    }
    active = [d for d in candidates if any(s <= d <= e for s, e in windows.values())]

    if not active:
        print(
            f"No World Cup is active around {today} "
            f"(checked {days + 1} day(s)); nothing to scrape."
        )
        return []

    results: list[MatchScrape] = []
    gid_year = _discover_dates(browser, [d.strftime("%Y%m%d") for d in active])
    print(f"recent: discovered {len(gid_year)} matches over {len(active)} day(s)")
    for gid, year in gid_year.items():
        _process_game(browser, gid, year, conn, results)
    return results

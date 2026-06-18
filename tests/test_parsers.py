"""Parser tests against saved rendered-HTML fixtures (no network)."""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from wc_scraper import discovery, parsers

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _scrape(name: str, year: int, game_id: str):
    return parsers.parse_match(
        game_id=game_id,
        year=year,
        lineups_html=_load(name),
        matchstats_html="",
        lineups_url=f"https://www.espn.com/soccer/lineups/_/gameId/{game_id}",
    )


# --- discovery -------------------------------------------------------------

def test_scoreboard_yields_game_id():
    ids = discovery.parse_schedule(_load("scoreboard_20100711.html"))
    assert ids == ["264123"]


# --- full squad layout (2014+) ---------------------------------------------

def test_full_layout_two_full_squads():
    s = _scrape("lineups_760436.html", 2026, "760436")
    assert s.match.home_team == "Uzbekistan"
    assert s.match.away_team == "Colombia"
    assert (s.match.home_score, s.match.away_score) == (1, 3)

    by_team = collections.Counter(st.team_name for st in s.stats)
    assert by_team == {"Uzbekistan": 26, "Colombia": 26}


def test_full_layout_jerseys_are_real_and_unique():
    s = _scrape("lineups_760436.html", 2026, "760436")
    col = {st.full_name.split()[-1]: st.jersey_number for st in s.stats if st.team_name == "Colombia"}
    # Known shirt numbers; Munoz scored, which previously polluted his jersey.
    assert col["Munoz"] == 2
    assert col["Rodriguez"] == 10
    assert col["Ospina"] == 1

    for team in ("Uzbekistan", "Colombia"):
        nums = [st.jersey_number for st in s.stats if st.team_name == team and st.jersey_number]
        assert len(nums) == len(set(nums)), "jersey numbers must be unique within a team"


def test_full_layout_carries_athlete_ids():
    s = _scrape("lineups_760436.html", 2026, "760436")
    assert all(st.espn_athlete_id for st in s.stats)


# --- sparse "key matchups" layout (2010 and earlier) -----------------------

def test_sparse_layout_few_players_split_by_team():
    s = _scrape("lineups_264123.html", 2010, "264123")
    assert s.match.home_team == "Netherlands"
    assert s.match.away_team == "Spain"
    assert (s.match.home_score, s.match.away_score) == (0, 1)

    names = {st.full_name for st in s.stats}
    assert "Iker Casillas" in names
    by_team = collections.Counter(st.team_name for st in s.stats)
    assert by_team == {"Netherlands": 3, "Spain": 3}


def test_sparse_layout_jersey_is_null_not_wrong():
    # The matchup widget shows stat values, not shirt numbers, so we must not guess.
    s = _scrape("lineups_264123.html", 2010, "264123")
    assert all(st.jersey_number is None for st in s.stats)
    # None of these six scored; goals are best-effort here, so accept 0 or unknown (None)
    # but never a spurious nonzero value.
    assert all(st.goals in (None, 0) for st in s.stats)


# --- robustness ------------------------------------------------------------

def test_garbage_html_does_not_crash():
    s = parsers.parse_match(
        game_id="0", year=1970, lineups_html="<html><body>nope</body></html>",
        matchstats_html="", lineups_url="u",
    )
    assert s.stats == []

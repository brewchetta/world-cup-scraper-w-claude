"""Public read endpoints (no API key required)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from . import queries
from .db import connection
from .schemas import (
    MatchDetailOut,
    MatchOut,
    PlayerMatchStatOut,
    PlayerOut,
    TeamOut,
    TournamentOut,
    TournamentTotalsOut,
)

router = APIRouter(tags=["read"])


@router.get("/tournaments", response_model=list[TournamentOut])
def list_tournaments():
    with connection() as conn:
        return queries.list_tournaments(conn)


@router.get("/tournaments/{year}", response_model=TournamentOut)
def get_tournament(year: int):
    with connection() as conn:
        row = queries.get_tournament(conn, year)
    if row is None:
        raise HTTPException(404, f"No tournament for year {year}")
    return row


@router.get("/tournaments/{year}/top-scorers", response_model=list[TournamentTotalsOut])
def top_scorers(year: int, limit: int = Query(20, ge=1, le=100)):
    with connection() as conn:
        return queries.tournament_top_scorers(conn, year, limit)


@router.get("/teams", response_model=list[TeamOut])
def list_teams(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    with connection() as conn:
        return queries.list_teams(conn, limit, offset)


@router.get("/players", response_model=list[PlayerOut])
def list_players(
    name: str | None = Query(None, description="Case-insensitive substring match"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with connection() as conn:
        return queries.search_players(conn, name, limit, offset)


@router.get("/players/{player_id}", response_model=PlayerOut)
def get_player(player_id: int):
    with connection() as conn:
        row = queries.get_player(conn, player_id)
    if row is None:
        raise HTTPException(404, f"No player with id {player_id}")
    return row


@router.get("/players/{player_id}/totals")
def player_totals(player_id: int):
    with connection() as conn:
        row = queries.player_career_totals(conn, player_id)
    if row is None:
        raise HTTPException(404, f"No stats for player id {player_id}")
    return row


@router.get("/matches", response_model=list[MatchOut])
def list_matches(
    year: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with connection() as conn:
        return queries.list_matches(conn, year, limit, offset)


@router.get("/matches/{match_id}", response_model=MatchDetailOut)
def get_match(match_id: int):
    with connection() as conn:
        match = queries.get_match(conn, match_id)
        if match is None:
            raise HTTPException(404, f"No match with id {match_id}")
        stats = queries.get_match_stats(conn, match_id)
    return {**match, "stats": [PlayerMatchStatOut(**s) for s in stats]}

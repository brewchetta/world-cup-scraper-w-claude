"""Typed records produced by the parsers and consumed by the loader.

These are deliberately simple value objects. Every scraped stat is Optional because
older tournaments (and many match reports) do not expose minutes/fouls per player.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Tournament(BaseModel):
    year: int
    host: Optional[str] = None
    start_date: Optional[str] = None  # ISO date string
    end_date: Optional[str] = None
    winner_team: Optional[str] = None


class Team(BaseModel):
    name: str
    country_code: Optional[str] = None
    confederation: Optional[str] = None


class Player(BaseModel):
    full_name: str
    espn_athlete_id: Optional[int] = None
    dob: Optional[str] = None
    primary_position: Optional[str] = None


class Match(BaseModel):
    espn_game_id: str
    year: int
    round: Optional[str] = None
    kickoff_utc: Optional[datetime] = None
    venue: Optional[str] = None
    home_team: str
    away_team: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class PlayerMatchStat(BaseModel):
    espn_game_id: str
    team_name: str
    full_name: str
    espn_athlete_id: Optional[int] = None
    jersey_number: Optional[int] = None
    position: Optional[str] = None
    is_starter: Optional[bool] = None
    minutes_played: Optional[int] = None
    goals: Optional[int] = None
    fouls_committed: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    source_url: Optional[str] = None


class MatchScrape(BaseModel):
    """Everything parsed from one match's pages."""

    match: Match
    teams: list[Team]
    players: list[Player]
    stats: list[PlayerMatchStat]

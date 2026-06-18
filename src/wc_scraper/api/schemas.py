"""Pydantic response models for the API (separate from scraper ingest models)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class TournamentOut(BaseModel):
    year: int
    host: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    winner_team: Optional[str] = None


class TeamOut(BaseModel):
    id: int
    name: str
    country_code: Optional[str] = None
    confederation: Optional[str] = None


class PlayerOut(BaseModel):
    id: int
    espn_athlete_id: Optional[int] = None
    full_name: str
    primary_position: Optional[str] = None


class MatchOut(BaseModel):
    id: int
    espn_game_id: str
    year: int
    round: Optional[str] = None
    kickoff_utc: Optional[datetime] = None
    venue: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class PlayerMatchStatOut(BaseModel):
    player_id: int
    full_name: str
    team_name: str
    jersey_number: Optional[int] = None
    position: Optional[str] = None
    is_starter: Optional[bool] = None
    minutes_played: Optional[int] = None
    goals: Optional[int] = None
    fouls_committed: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None


class MatchDetailOut(MatchOut):
    stats: list[PlayerMatchStatOut] = []


class TournamentTotalsOut(BaseModel):
    year: int
    full_name: str
    team_name: str
    matches_played: int
    goals: int
    minutes_played: Optional[int] = None
    fouls_committed: Optional[int] = None
    yellow_cards: int
    red_cards: int


class ApiKeyOut(BaseModel):
    id: int
    client_name: str
    key_prefix: str
    role: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ApiKeyCreatedOut(BaseModel):
    id: int
    client_name: str
    role: str
    key: str  # plaintext, shown once


class WhoAmIOut(BaseModel):
    client_name: str
    role: str

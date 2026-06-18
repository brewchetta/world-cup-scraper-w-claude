"""Idempotent loading of scraped records into Postgres/Supabase via psycopg."""

from __future__ import annotations

from pathlib import Path

import psycopg

from ..models import MatchScrape, Tournament

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def init_db(conn: psycopg.Connection) -> None:
    """Create tables/views. Safe to run repeatedly."""
    conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def _upsert_tournament(conn: psycopg.Connection, t: Tournament) -> int:
    row = conn.execute(
        """
        INSERT INTO tournaments (year, host, start_date, end_date, winner_team)
        VALUES (%(year)s, %(host)s, %(start_date)s, %(end_date)s, %(winner_team)s)
        ON CONFLICT (year) DO UPDATE SET
            host = COALESCE(EXCLUDED.host, tournaments.host),
            start_date = COALESCE(EXCLUDED.start_date, tournaments.start_date),
            end_date = COALESCE(EXCLUDED.end_date, tournaments.end_date),
            winner_team = COALESCE(EXCLUDED.winner_team, tournaments.winner_team)
        RETURNING id
        """,
        t.model_dump(),
    ).fetchone()
    return row[0]


def _upsert_team(conn: psycopg.Connection, name: str) -> int:
    row = conn.execute(
        """
        INSERT INTO teams (name) VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (name,),
    ).fetchone()
    return row[0]


def _upsert_player(
    conn: psycopg.Connection,
    full_name: str,
    position: str | None,
    espn_athlete_id: int | None,
) -> int:
    # Prefer the stable ESPN athlete id; fall back to (full_name, dob) when it's absent.
    if espn_athlete_id is not None:
        row = conn.execute(
            """
            INSERT INTO players (espn_athlete_id, full_name, primary_position)
            VALUES (%s, %s, %s)
            ON CONFLICT (espn_athlete_id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                primary_position = COALESCE(EXCLUDED.primary_position, players.primary_position)
            RETURNING id
            """,
            (espn_athlete_id, full_name, position),
        ).fetchone()
    else:
        row = conn.execute(
            """
            INSERT INTO players (full_name, primary_position) VALUES (%s, %s)
            ON CONFLICT (full_name, (COALESCE(dob, DATE '0001-01-01')))
                WHERE espn_athlete_id IS NULL
            DO UPDATE SET
                primary_position = COALESCE(EXCLUDED.primary_position, players.primary_position)
            RETURNING id
            """,
            (full_name, position),
        ).fetchone()
    return row[0]


def load_match(conn: psycopg.Connection, scrape: MatchScrape) -> None:
    """Upsert one fully-parsed match (tournament, teams, players, match, stats)."""
    m = scrape.match
    tournament_id = _upsert_tournament(conn, Tournament(year=m.year))

    team_ids = {name: _upsert_team(conn, name) for name in {m.home_team, m.away_team}}

    match_id = conn.execute(
        """
        INSERT INTO matches (espn_game_id, tournament_id, round, kickoff_utc, venue,
                             home_team_id, away_team_id, home_score, away_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (espn_game_id) DO UPDATE SET
            round = COALESCE(EXCLUDED.round, matches.round),
            kickoff_utc = COALESCE(EXCLUDED.kickoff_utc, matches.kickoff_utc),
            venue = COALESCE(EXCLUDED.venue, matches.venue),
            home_score = COALESCE(EXCLUDED.home_score, matches.home_score),
            away_score = COALESCE(EXCLUDED.away_score, matches.away_score)
        RETURNING id
        """,
        (
            m.espn_game_id, tournament_id, m.round, m.kickoff_utc, m.venue,
            team_ids[m.home_team], team_ids[m.away_team], m.home_score, m.away_score,
        ),
    ).fetchone()[0]

    # Build a position lookup so the player row can carry a primary position.
    position_by_name = {p.full_name: p.primary_position for p in scrape.players}

    for s in scrape.stats:
        team_id = team_ids.get(s.team_name) or _upsert_team(conn, s.team_name)
        player_id = _upsert_player(
            conn, s.full_name, position_by_name.get(s.full_name), s.espn_athlete_id
        )
        conn.execute(
            """
            INSERT INTO player_match_stats
                (match_id, player_id, team_id, jersey_number, position, is_starter,
                 minutes_played, goals, fouls_committed, yellow_cards, red_cards, source_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (match_id, player_id) DO UPDATE SET
                jersey_number   = COALESCE(EXCLUDED.jersey_number, player_match_stats.jersey_number),
                position        = COALESCE(EXCLUDED.position, player_match_stats.position),
                is_starter      = COALESCE(EXCLUDED.is_starter, player_match_stats.is_starter),
                minutes_played  = COALESCE(EXCLUDED.minutes_played, player_match_stats.minutes_played),
                goals           = COALESCE(EXCLUDED.goals, player_match_stats.goals),
                fouls_committed = COALESCE(EXCLUDED.fouls_committed, player_match_stats.fouls_committed),
                yellow_cards    = COALESCE(EXCLUDED.yellow_cards, player_match_stats.yellow_cards),
                red_cards       = COALESCE(EXCLUDED.red_cards, player_match_stats.red_cards),
                source_url      = COALESCE(EXCLUDED.source_url, player_match_stats.source_url),
                scraped_at      = now()
            """,
            (
                match_id, player_id, team_id, s.jersey_number, s.position, s.is_starter,
                s.minutes_played, s.goals, s.fouls_committed, s.yellow_cards,
                s.red_cards, s.source_url,
            ),
        )

    conn.commit()

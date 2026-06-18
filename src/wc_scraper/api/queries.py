"""Read queries against the World Cup tables/views. Returns dict rows."""

from __future__ import annotations

import psycopg


def list_tournaments(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        "SELECT year, host, start_date, end_date, winner_team FROM tournaments ORDER BY year"
    ).fetchall()


def get_tournament(conn: psycopg.Connection, year: int) -> dict | None:
    return conn.execute(
        "SELECT year, host, start_date, end_date, winner_team FROM tournaments WHERE year = %s",
        (year,),
    ).fetchone()


def list_teams(conn: psycopg.Connection, limit: int, offset: int) -> list[dict]:
    return conn.execute(
        "SELECT id, name, country_code, confederation FROM teams ORDER BY name LIMIT %s OFFSET %s",
        (limit, offset),
    ).fetchall()


def get_player(conn: psycopg.Connection, player_id: int) -> dict | None:
    return conn.execute(
        "SELECT id, espn_athlete_id, full_name, primary_position FROM players WHERE id = %s",
        (player_id,),
    ).fetchone()


def search_players(conn: psycopg.Connection, name: str | None, limit: int, offset: int) -> list[dict]:
    if name:
        return conn.execute(
            """
            SELECT id, espn_athlete_id, full_name, primary_position
            FROM players WHERE full_name ILIKE %s ORDER BY full_name LIMIT %s OFFSET %s
            """,
            (f"%{name}%", limit, offset),
        ).fetchall()
    return conn.execute(
        "SELECT id, espn_athlete_id, full_name, primary_position FROM players ORDER BY full_name LIMIT %s OFFSET %s",
        (limit, offset),
    ).fetchall()


_MATCH_SELECT = """
    SELECT m.id, m.espn_game_id, t.year, m.round, m.kickoff_utc, m.venue,
           h.name AS home_team, a.name AS away_team, m.home_score, m.away_score
    FROM matches m
    JOIN tournaments t ON t.id = m.tournament_id
    LEFT JOIN teams h ON h.id = m.home_team_id
    LEFT JOIN teams a ON a.id = m.away_team_id
"""


def list_matches(conn: psycopg.Connection, year: int | None, limit: int, offset: int) -> list[dict]:
    if year is not None:
        return conn.execute(
            _MATCH_SELECT + " WHERE t.year = %s ORDER BY m.kickoff_utc LIMIT %s OFFSET %s",
            (year, limit, offset),
        ).fetchall()
    return conn.execute(
        _MATCH_SELECT + " ORDER BY m.kickoff_utc LIMIT %s OFFSET %s", (limit, offset)
    ).fetchall()


def get_match(conn: psycopg.Connection, match_id: int) -> dict | None:
    return conn.execute(_MATCH_SELECT + " WHERE m.id = %s", (match_id,)).fetchone()


def get_match_stats(conn: psycopg.Connection, match_id: int) -> list[dict]:
    return conn.execute(
        """
        SELECT pms.player_id, p.full_name, tm.name AS team_name, pms.jersey_number,
               pms.position, pms.is_starter, pms.minutes_played, pms.goals,
               pms.fouls_committed, pms.yellow_cards, pms.red_cards
        FROM player_match_stats pms
        JOIN players p ON p.id = pms.player_id
        JOIN teams tm ON tm.id = pms.team_id
        WHERE pms.match_id = %s
        ORDER BY tm.name, pms.jersey_number NULLS LAST
        """,
        (match_id,),
    ).fetchall()


def player_career_totals(conn: psycopg.Connection, player_id: int) -> dict | None:
    return conn.execute(
        "SELECT * FROM v_player_career_totals WHERE player_id = %s", (player_id,)
    ).fetchone()


def tournament_top_scorers(conn: psycopg.Connection, year: int, limit: int) -> list[dict]:
    return conn.execute(
        """
        SELECT year, full_name, team_name, matches_played, goals,
               minutes_played, fouls_committed, yellow_cards, red_cards
        FROM v_player_tournament_totals
        WHERE year = %s ORDER BY goals DESC, full_name LIMIT %s
        """,
        (year, limit),
    ).fetchall()

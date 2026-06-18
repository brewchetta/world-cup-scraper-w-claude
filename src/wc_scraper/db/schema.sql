-- FIFA World Cup player-stats schema (per-match grain).
-- Idempotent: safe to run repeatedly. All stat columns are nullable because older
-- tournaments do not expose minutes/fouls per player.

CREATE TABLE IF NOT EXISTS tournaments (
    id          SERIAL PRIMARY KEY,
    year        INTEGER NOT NULL UNIQUE,
    host        TEXT,
    start_date  DATE,
    end_date    DATE,
    winner_team TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    country_code  TEXT,
    confederation TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id               SERIAL PRIMARY KEY,
    espn_athlete_id  INTEGER UNIQUE,        -- stable id from the player-link href
    full_name        TEXT NOT NULL,
    dob              DATE,
    primary_position TEXT
);

-- Fallback natural key ONLY for rows that lack an ESPN athlete id (e.g. sparse old pages).
-- It must be a PARTIAL index: distinct people legitimately share a name (two Luis Suarez),
-- and those are kept apart by espn_athlete_id -- so name uniqueness applies only when there
-- is no athlete id. A plain UNIQUE(full_name, dob) would also treat each NULL dob as
-- distinct, hence the COALESCE to a sentinel date.
CREATE UNIQUE INDEX IF NOT EXISTS uq_players_name_dob
    ON players (full_name, (COALESCE(dob, DATE '0001-01-01')))
    WHERE espn_athlete_id IS NULL;

CREATE TABLE IF NOT EXISTS matches (
    id            SERIAL PRIMARY KEY,
    espn_game_id  TEXT NOT NULL UNIQUE,
    tournament_id INTEGER NOT NULL REFERENCES tournaments (id),
    round         TEXT,
    kickoff_utc   TIMESTAMPTZ,
    venue         TEXT,
    home_team_id  INTEGER REFERENCES teams (id),
    away_team_id  INTEGER REFERENCES teams (id),
    home_score    INTEGER,
    away_score    INTEGER
);

CREATE TABLE IF NOT EXISTS player_match_stats (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches (id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL REFERENCES players (id),
    team_id         INTEGER NOT NULL REFERENCES teams (id),
    jersey_number   INTEGER,
    position        TEXT,
    is_starter      BOOLEAN,
    minutes_played  INTEGER,
    goals           INTEGER,
    fouls_committed INTEGER,
    yellow_cards    INTEGER,
    red_cards       INTEGER,
    source_url      TEXT,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_pms_player ON player_match_stats (player_id);
CREATE INDEX IF NOT EXISTS idx_pms_team   ON player_match_stats (team_id);
CREATE INDEX IF NOT EXISTS idx_matches_tournament ON matches (tournament_id);

-- Per-tournament totals per player (derived; the future API reads these).
CREATE OR REPLACE VIEW v_player_tournament_totals AS
SELECT
    t.year,
    p.id   AS player_id,
    p.full_name,
    tm.name AS team_name,
    COUNT(DISTINCT pms.match_id)        AS matches_played,
    SUM(COALESCE(pms.goals, 0))         AS goals,
    SUM(pms.minutes_played)             AS minutes_played,
    SUM(pms.fouls_committed)            AS fouls_committed,
    SUM(COALESCE(pms.yellow_cards, 0))  AS yellow_cards,
    SUM(COALESCE(pms.red_cards, 0))     AS red_cards
FROM player_match_stats pms
JOIN matches m     ON m.id = pms.match_id
JOIN tournaments t ON t.id = m.tournament_id
JOIN players p     ON p.id = pms.player_id
JOIN teams tm      ON tm.id = pms.team_id
GROUP BY t.year, p.id, p.full_name, tm.name;

-- All-time career totals per player (across tournaments).
CREATE OR REPLACE VIEW v_player_career_totals AS
SELECT
    p.id AS player_id,
    p.full_name,
    COUNT(DISTINCT pms.match_id)       AS matches_played,
    COUNT(DISTINCT m.tournament_id)    AS tournaments_played,
    SUM(COALESCE(pms.goals, 0))        AS goals,
    SUM(pms.minutes_played)            AS minutes_played,
    SUM(pms.fouls_committed)           AS fouls_committed
FROM player_match_stats pms
JOIN matches m ON m.id = pms.match_id
JOIN players p ON p.id = pms.player_id
GROUP BY p.id, p.full_name;

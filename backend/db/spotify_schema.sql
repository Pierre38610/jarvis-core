-- db/spotify_schema.sql
-- Tables SQLite pour l integration Spotify de J.A.R.V.I.S.

CREATE TABLE IF NOT EXISTS spotify_tokens (
    id                  INTEGER     PRIMARY KEY DEFAULT 1,
    access_token_enc    TEXT        NOT NULL,
    refresh_token_enc   TEXT        NOT NULL,
    expires_at          REAL        NOT NULL,
    scope               TEXT        NOT NULL DEFAULT '',
    token_type          TEXT        NOT NULL DEFAULT 'Bearer',
    spotify_user_id     TEXT        NOT NULL DEFAULT '',
    display_name        TEXT        NOT NULL DEFAULT '',
    created_at          TEXT        NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT        NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS spotify_device_aliases (
    alias               TEXT        PRIMARY KEY,
    device_type         TEXT,
    device_name_pattern TEXT
);

INSERT OR IGNORE INTO spotify_device_aliases (alias, device_type, device_name_pattern) VALUES
    ('pc',          'Computer',    NULL),
    ('ordi',        'Computer',    NULL),
    ('ordinateur',  'Computer',    NULL),
    ('portable',    'Computer',    NULL),
    ('laptop',      'Computer',    NULL),
    ('telephone',   'Smartphone',  NULL),
    ('tel',         'Smartphone',  NULL),
    ('mobile',      'Smartphone',  NULL),
    ('phone',       'Smartphone',  NULL),
    ('enceinte',    'Speaker',     NULL),
    ('speaker',     'Speaker',     NULL),
    ('sono',        'Speaker',     NULL),
    ('tv',          'TV',          NULL),
    ('tele',        'TV',          NULL);

CREATE TABLE IF NOT EXISTS migration_state (
    id                  INTEGER     PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT        NOT NULL DEFAULT '',
    source_playlist     TEXT        NOT NULL DEFAULT '',
    deezer_track_id     INTEGER     NOT NULL,
    deezer_title        TEXT        NOT NULL DEFAULT '',
    deezer_artist       TEXT        NOT NULL DEFAULT '',
    deezer_album        TEXT        NOT NULL DEFAULT '',
    deezer_isrc         TEXT        NOT NULL DEFAULT '',
    deezer_duration_s   REAL        NOT NULL DEFAULT 0,
    spotify_track_id    TEXT        NOT NULL DEFAULT '',
    spotify_title       TEXT        NOT NULL DEFAULT '',
    spotify_artist      TEXT        NOT NULL DEFAULT '',
    confidence_score    REAL        NOT NULL DEFAULT 0.0,
    duration_delta_s    REAL        NOT NULL DEFAULT 0.0,
    match_method        TEXT        NOT NULL DEFAULT '',
    status              TEXT        NOT NULL DEFAULT 'pending',
    error_msg           TEXT        NOT NULL DEFAULT '',
    created_at          TEXT        NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT        NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_migration_run_id ON migration_state (run_id);
CREATE INDEX IF NOT EXISTS idx_migration_playlist ON migration_state (source_playlist);
CREATE INDEX IF NOT EXISTS idx_migration_status ON migration_state (status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_migration_unique ON migration_state (run_id, source_playlist, deezer_track_id);

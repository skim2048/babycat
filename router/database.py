"""Babycat router — account database (users, refresh tokens, WHEP session registry). @claude"""

import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/data/db/router.db")

# @claude token_epoch backs immediate revocation (SDD §6.2): logout/password
# @claude change bumps it, invalidating every access token minted before.
# @claude failed_count/locked_until persist the login limiter (FR-007) so a
# @claude container restart cannot bypass a lockout.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL UNIQUE,
    password_hash    TEXT    NOT NULL,
    salt             TEXT    NOT NULL,
    password_changed INTEGER NOT NULL DEFAULT 0,
    token_epoch      INTEGER NOT NULL DEFAULT 0,
    failed_count     INTEGER NOT NULL DEFAULT 0,
    locked_until     REAL    NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT    NOT NULL UNIQUE,
    username    TEXT    NOT NULL,
    expires_at  INTEGER NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_username ON refresh_tokens(username);

CREATE TABLE IF NOT EXISTS whep_sessions (
    session_path TEXT    PRIMARY KEY,
    username     TEXT    NOT NULL,
    created_at   INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_whep_sessions_username ON whep_sessions(username);

-- @claude Client-defined data, one JSON document per (account, key). Stored
-- @claude opaquely (FR-059): the router persists what the client asks it to
-- @claude keep — reinstalling the client must not lose it — and never
-- @claude interprets the content. Domain knowledge stays in the client.
CREATE TABLE IF NOT EXISTS client_storage (
    username   TEXT NOT NULL,
    key        TEXT NOT NULL,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (username, key)
);
"""


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_db():
    # @claude FastAPI runs sync generator dependencies in a threadpool, and the
    # @claude setup and teardown may land on different workers (SDD §5.2). Each
    # @claude request still owns its connection exclusively, so cross-thread
    # @claude sequential use is safe.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

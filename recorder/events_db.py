"""Babycat recorder — event history database (FR-031, SDD §5.2)."""

import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/data/db/recorder.db")

# @claude Column names are kept from the prototype so the external contract
# @claude (EventOut: id/trigger/clip_name/created_at) survives the split.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger    TEXT    NOT NULL,
    clip_name  TEXT,
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
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


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_event(trigger: str, clip_name: str | None, created_at: str) -> None:
    """Record one event occurrence; called from the finalize worker thread.
    created_at is the judgment moment (FR-031), not the DB write moment —
    finalize runs seconds after the event to wait out the post window."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO events (trigger, clip_name, created_at) VALUES (?, ?, ?)",
            (trigger, clip_name, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def delete_events_for_clips(clip_names: list[str]) -> int:
    """Delete history rows tied to clips removed by automatic pruning (FR-033)."""
    if not clip_names:
        return 0
    conn = _connect()
    try:
        marks = ",".join("?" for _ in clip_names)
        cur = conn.execute(f"DELETE FROM events WHERE clip_name IN ({marks})", clip_names)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()

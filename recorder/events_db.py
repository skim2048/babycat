"""Babycat recorder — event/inference history database (FR-031, SDD §5.2)."""

import logging
import sqlite3
import time
from pathlib import Path

from settings import DB_PATH, INFERENCE_RETENTION_DAYS

log = logging.getLogger(__name__)

# @claude 기본 90일 — 클라이언트 화면 요구(당일 + 기준선 14일 + 월 단위 회고)를
# @claude 근거로 상향(analysis-mewly-impl.md §5). 10초 주기 기준 약 78만 행.

# @claude Column names are kept from the prototype so the external contract
# @claude (EventOut: id/trigger/clip_name/created_at) survives the split.
# @claude `inferences` is the 2층 history: every inference, matched or not,
# @claude with the raw text preserved so labels can be re-derived after a
# @claude vocabulary change. Its lifetime is independent of clips (FR-033
# @claude deletion never touches it).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger    TEXT    NOT NULL,
    clip_name  TEXT,
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE TABLE IF NOT EXISTS inferences (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL,
    vlm_text   TEXT    NOT NULL,
    labels     TEXT    NOT NULL DEFAULT '[]',
    preset     TEXT    NOT NULL DEFAULT 'default',
    model      TEXT    NOT NULL DEFAULT '',
    elapsed_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_inferences_created_at ON inferences(created_at);
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
    # @claude check_same_thread=False: FastAPI runs a sync dependency's setup
    # @claude (connection creation in get_db) and the sync endpoint body on
    # @claude threadpool threads that may differ, which violates sqlite3's
    # @claude default same-thread rule intermittently (the /summary 500s,
    # @claude analysis-mewly-impl.md §8). Each request still owns its private
    # @claude connection and uses it sequentially, so cross-thread hand-off is
    # @claude safe with the serialized sqlite3 build CPython ships.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # @claude The finalize worker thread and request handlers open their own
    # @claude connections; a write from one waits for the other instead of
    # @claude failing with "database is locked" (SDD §5.2).
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


_last_prune_at = 0.0


def insert_inference(created_at: str, vlm_text: str, labels_json: str,
                     preset: str, model: str, elapsed_ms: int | None) -> None:
    """Append one inference row (2층 이력); called from the notify handler."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO inferences (created_at, vlm_text, labels, preset, model, elapsed_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (created_at, vlm_text, labels_json, preset, model, elapsed_ms),
        )
        conn.commit()
    finally:
        conn.close()
    _maybe_prune_inferences()


def _maybe_prune_inferences() -> None:
    """Drop rows older than the retention window, at most once per hour.
    Retention is time-based only for now (INFERENCE_RETENTION_DAYS). @claude"""
    global _last_prune_at
    now = time.time()
    if now - _last_prune_at < 3600:
        return
    _last_prune_at = now
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(now - INFERENCE_RETENTION_DAYS * 86400),
    )
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM inferences WHERE created_at < ?", (cutoff,))
        conn.commit()
        if cur.rowcount:
            log.info("inference history pruned: %d rows (< %s)", cur.rowcount, cutoff)
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

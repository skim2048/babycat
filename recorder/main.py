"""
Babycat recorder — event clips, history, hardware status.

Internal only: the router relays external clip/history requests here, and
the analyzer posts event notifications (SDD §4.4, §6.3). Owns the event
database and the clip files exclusively.

@claude
"""

import json
import logging
import os
import re
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import finalize
import segments
from events_db import get_db, init_db
from hardware import HardwareMonitor, disk_usage
from status import status

log = logging.getLogger(__name__)

CLIP_DIR = os.getenv("CLIP_DIR", "/data/clips")
STATE_PATH = os.getenv("STATE_PATH", "/data/state/recorder.json")
MIN_CLIP_SIZE = 10240  # @claude 10KB — excludes partially-written files.

_hw = HardwareMonitor()


# ── Buffer-active persistence (FR-014) ───────────────────────────────────────


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    init_db()
    Path(CLIP_DIR).mkdir(parents=True, exist_ok=True)
    if _load_state().get("buffer_active"):
        # @claude Restore the pre-restart operating state (FR-014, SDD §3.5).
        status.set_buffer_active(True)
        segments.recorder.start()
        log.info("buffer restored to active state")
    yield


app = FastAPI(title="Babycat recorder", version="1.0.0", lifespan=lifespan)


class ClipOut(BaseModel):
    name: str
    size: int
    created_at: str
    timestamp: Optional[int] = None
    keywords: list[str] = []
    vlm_text: Optional[str] = None


class ClipListOut(BaseModel):
    clips: list[ClipOut]
    total: int


class ClipDeleteIn(BaseModel):
    names: list[str]


class DeletedOut(BaseModel):
    deleted: int


class EventOut(BaseModel):
    id: int
    trigger: str
    clip_name: Optional[str]
    created_at: str


class EventListOut(BaseModel):
    events: list[EventOut]
    total: int


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Analysis-start fan-out and event notification ────────────────────────────


@app.post("/buffer/start")
def buffer_start():
    """Start the pre-event segment buffer (SRS §2.3 (5), SDD §2.4 (4)). Idempotent."""
    status.set_buffer_active(True)
    _save_state({"buffer_active": True})
    segments.recorder.start()
    return {"ok": True}


@app.post("/buffer/stop")
def buffer_stop():
    """Stop the pre-event segment buffer (FR-049, FR-051). Idempotent."""
    status.set_buffer_active(False)
    _save_state({"buffer_active": False})
    segments.recorder.stop()
    return {"ok": True}


@app.post("/notify", status_code=202)
async def notify(request: Request):
    """Event notification from the analyzer (SDD §6.3). Responds immediately;
    clip assembly and history recording continue on a worker thread."""
    payload = await request.json()
    accepted = finalize.accept_event(payload)
    return {"ok": True, "accepted": accepted}


# ── Clips ────────────────────────────────────────────────────────────────────


def _read_clip_meta(mp4_path: Path) -> dict:
    meta_path = mp4_path.with_suffix(".json")
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_date_query(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, f"invalid {name}") from exc


def _local_date_bound_utc(value: str, end: bool) -> str:
    """Convert a local-calendar date to the matching UTC timestamp string.

    Date filters mean the system-local (TZ) calendar day — the same rule the
    clip listing applies — while created_at stays stored in UTC, so the
    boundary must be converted rather than string-compared.

    @claude
    """
    local = datetime.strptime(value, "%Y-%m-%d")
    if end:
        local = local.replace(hour=23, minute=59, second=59)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _list_clips(q: str | None, date_from: str | None, date_to: str | None) -> list[ClipOut]:
    base = Path(CLIP_DIR)
    if not base.exists():
        return []

    entries = []
    for f in base.rglob("*.mp4"):
        st = f.stat()
        if st.st_size >= MIN_CLIP_SIZE:
            entries.append((f, st.st_size, st.st_mtime))

    entries.sort(key=lambda e: e[2], reverse=True)
    clips = []
    for fpath, size, mtime in entries:
        meta = _read_clip_meta(fpath)
        if not meta:
            continue
        if q:
            vlm_text = meta.get("vlm_text")
            if not isinstance(vlm_text, str) or q.lower() not in vlm_text.lower():
                continue
        if date_from or date_to:
            ts = meta.get("timestamp", int(mtime))
            clip_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            if date_from and clip_date < date_from:
                continue
            if date_to and clip_date > date_to:
                continue
        clips.append(ClipOut(
            name=fpath.name,
            size=size,
            created_at=datetime.fromtimestamp(mtime, tz=timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"),
            timestamp=meta.get("timestamp", int(mtime)),
            keywords=meta.get("keywords", []),
            vlm_text=meta.get("vlm_text"),
        ))
    return clips


def _resolve_clip(name: str) -> Path | None:
    if "/" in name or "\\" in name or ".." in name:
        return None
    base = Path(CLIP_DIR)
    if len(name) >= 8 and name[:8].isdigit():
        candidate = base / name[:4] / name[4:6] / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for path in base.rglob(name):
        if path.is_file():
            return path
    return None


def _parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    match = re.match(r"bytes=(\d+)-(\d*)", range_header or "")
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return None
    return start, end


@app.get("/clips", response_model=ClipListOut)
def list_clips(
    q: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(10, ge=1),
    offset: int = Query(0, ge=0),
):
    date_from = _normalize_date_query("date_from", date_from)
    date_to = _normalize_date_query("date_to", date_to)
    all_clips = _list_clips(q, date_from, date_to)
    return ClipListOut(clips=all_clips[offset:offset + limit], total=len(all_clips))


@app.get("/clips/{name}")
def get_clip(name: str, request: Request):
    fpath = _resolve_clip(name)
    if fpath is None:
        raise HTTPException(404, "clip not found")
    file_size = fpath.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(fpath, media_type="video/mp4")

    byte_range = _parse_byte_range(range_header, file_size)
    if byte_range is None:
        raise HTTPException(416, "invalid range")
    start, end = byte_range
    length = end - start + 1

    def iter_range():
        with open(fpath, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_range(),
        status_code=206,
        media_type="video/mp4",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


@app.delete("/clips", response_model=DeletedOut)
def delete_clips(body: ClipDeleteIn):
    """User deletion removes the clip+sidecar pair; history stays (SDD §5.5).
    Capacity pruning (FR-033) runs concurrently and may win the race for any
    file — a clip that vanished underneath us is simply not ours to count."""
    deleted = 0
    for name in body.names:
        fpath = _resolve_clip(name)
        if fpath is None:
            continue
        try:
            fpath.unlink()
        except FileNotFoundError:
            continue
        fpath.with_suffix(".json").unlink(missing_ok=True)
        deleted += 1
    return DeletedOut(deleted=deleted)


@app.delete("/clips/all", response_model=DeletedOut)
def delete_all_clips():
    base = Path(CLIP_DIR)
    if not base.exists():
        return DeletedOut(deleted=0)
    deleted = 0
    for f in base.rglob("*.mp4"):
        if not f.is_file():
            continue
        try:
            f.unlink()
        except FileNotFoundError:
            continue
        f.with_suffix(".json").unlink(missing_ok=True)
        deleted += 1
    return DeletedOut(deleted=deleted)


# ── Event history ────────────────────────────────────────────────────────────


@app.get("/events", response_model=EventListOut)
def list_events(
    q: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    date_from = _normalize_date_query("date_from", date_from)
    date_to = _normalize_date_query("date_to", date_to)
    where, params = [], []
    if q:
        where.append("trigger LIKE ?")
        params.append(f"%{q}%")
    if date_from:
        where.append("created_at >= ?")
        params.append(_local_date_bound_utc(date_from, end=False))
    if date_to:
        where.append("created_at <= ?")
        params.append(_local_date_bound_utc(date_to, end=True))
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(f"SELECT COUNT(*) FROM events {clause}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT id, trigger, clip_name, created_at FROM events {clause} "
        "ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return EventListOut(events=[EventOut(**dict(r)) for r in rows], total=total)


@app.delete("/events/{event_id}", response_model=DeletedOut)
def delete_event(event_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "event not found")
    return DeletedOut(deleted=1)


@app.delete("/events", response_model=DeletedOut)
def delete_events(db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM events")
    return DeletedOut(deleted=cur.rowcount)


# ── Status (monitoring merge source, SDD §6.4 (4)) ───────────────────────────


@app.get("/status")
def get_status(db: sqlite3.Connection = Depends(get_db)):
    clip_count = sum(
        1 for f in Path(CLIP_DIR).rglob("*.mp4")
        if f.is_file() and f.stat().st_size >= MIN_CLIP_SIZE
    ) if Path(CLIP_DIR).exists() else 0
    return {
        **_hw.snapshot(),
        **disk_usage(CLIP_DIR),
        **status.snapshot(),
        "clip_count": clip_count,
        "event_count": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
    }

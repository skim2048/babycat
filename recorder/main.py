"""
Babycat recorder — event clips, history, hardware status.

Internal only: the router relays external clip/history requests here, and
the analyzer posts event notifications (SDD §4.4, §6.3). Owns the event
database and the clip files exclusively.

@claude
"""

import json
import logging
import re
import sqlite3
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import finalize
import segments
import state_store
from clip_storage import MIN_CLIP_SIZE, clip_count, count_removed_clip, recount_clips
from events_db import get_db, init_db, insert_inference
from hardware import HardwareMonitor, disk_usage
from settings import CLIP_DIR, STATE_PATH
from status import status

log = logging.getLogger(__name__)

_hw = HardwareMonitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    init_db()
    Path(CLIP_DIR).mkdir(parents=True, exist_ok=True)
    # @claude Crash leftovers (SDD §5.4): a .part clip or a .json.tmp sidecar
    # @claude whose writer died mid-write, and a torn state-file temp — sweep
    # @claude before seeding the counter.
    for pattern in ("*.part", "*.json.tmp"):
        for stale in Path(CLIP_DIR).rglob(pattern):
            stale.unlink(missing_ok=True)
    Path(f"{STATE_PATH}.tmp").unlink(missing_ok=True)
    # @claude One full walk at startup seeds the in-memory clip counter; every
    # @claude later mutation adjusts it (no per-poll tree walk in /status).
    log.info("clip counter seeded: %d clips", recount_clips(CLIP_DIR))
    if state_store.load().get("buffer_active"):
        # @claude Restore the pre-restart operating state (FR-014, SDD §3.5).
        status.set_buffer_active(True)
        segments.recorder.start()
        log.info("buffer restored to active state")
    yield


app = FastAPI(title="Babycat recorder", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_as_400(_request: Request, exc: RequestValidationError):
    """A malformed request is 400 (SDD §6.5), not FastAPI's default 422."""
    return JSONResponse(status_code=400, content={"detail": "invalid request body"})


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


class InferenceOut(BaseModel):
    id: int
    created_at: str
    vlm_text: str
    labels: list[str]
    preset: str
    model: str
    elapsed_ms: Optional[int]


class InferenceListOut(BaseModel):
    inferences: list[InferenceOut]
    total: int


# ── Analysis-start fan-out and event notification ────────────────────────────


@app.post("/buffer/start")
def buffer_start():
    """Start the pre-event segment buffer (SRS §2.3 (5), SDD §2.4 (4)). Idempotent."""
    status.set_buffer_active(True)
    state_store.update(buffer_active=True)
    segments.recorder.start()
    return {"ok": True}


@app.post("/buffer/stop")
def buffer_stop():
    """Stop the pre-event segment buffer (FR-049, FR-051). Idempotent."""
    status.set_buffer_active(False)
    state_store.update(buffer_active=False)
    segments.recorder.stop()
    return {"ok": True}


@app.post("/notify", status_code=202)
async def notify(request: Request):
    """Event notification from the analyzer (SDD §6.3). Responds immediately;
    clip assembly and history recording continue on a worker thread."""
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "invalid request body")
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid request body")
    accepted = finalize.accept_event(payload)
    return {"ok": True, "accepted": accepted}


@app.post("/inferences", status_code=202)
async def post_inference(request: Request):
    """Inference-history notification from the analyzer (layer-2 history). Every
    inference arrives here, matched or not; the raw text is preserved so
    labels can be re-derived after a vocabulary change."""
    payload = await request.json()
    vlm_text = payload.get("vlm_text")
    if not isinstance(vlm_text, str):
        raise HTTPException(400, "vlm_text required")
    judged_at = payload.get("judged_at")
    created_at = (
        datetime.fromtimestamp(judged_at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(judged_at, (int, float))
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    labels = payload.get("labels")
    labels = [l for l in labels if isinstance(l, str)] if isinstance(labels, list) else []
    elapsed = payload.get("inference_elapsed_ms")
    insert_inference(
        created_at,
        vlm_text,
        json.dumps(labels, ensure_ascii=False),
        str(payload.get("preset") or "default"),
        str(payload.get("model") or ""),
        elapsed if isinstance(elapsed, int) else None,
    )
    return {"ok": True}


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
        # @claude The video is the substance, the sidecar an accessory
        # @claude (SDD §5.3): a clip whose metadata write failed still lists,
        # @claude with fields falling back to file facts. This also keeps the
        # @claude listing rule identical to the clip counter's.
        meta = _read_clip_meta(fpath)
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
    # @claude Published clips only (SDD §5.4): an in-progress .part — or any
    # @claude non-mp4 file in the tree — is never a valid playback or
    # @claude deletion target.
    if not name.endswith(".mp4"):
        return None
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
            size = fpath.stat().st_size
            fpath.unlink()
        except FileNotFoundError:
            continue
        count_removed_clip(size)
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
            size = f.stat().st_size
            f.unlink()
        except FileNotFoundError:
            continue
        count_removed_clip(size)
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


@app.get("/inferences", response_model=InferenceListOut)
def list_inferences(
    label: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(200, ge=1),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    """Inference history (layer-2 history). `label` filters rows whose label list
    contains the exact label; date bounds follow the /events convention."""
    date_from = _normalize_date_query("date_from", date_from)
    date_to = _normalize_date_query("date_to", date_to)
    where, params = [], []
    if label:
        # @claude labels is a JSON array of strings; the quoted form matches
        # @claude exact members only (no substring false hits across labels).
        where.append("labels LIKE ?")
        params.append(f'%{json.dumps(label, ensure_ascii=False)}%')
    if date_from:
        where.append("created_at >= ?")
        params.append(_local_date_bound_utc(date_from, end=False))
    if date_to:
        where.append("created_at <= ?")
        params.append(_local_date_bound_utc(date_to, end=True))
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(f"SELECT COUNT(*) FROM inferences {clause}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT id, created_at, vlm_text, labels, preset, model, elapsed_ms "
        f"FROM inferences {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["labels"] = json.loads(d["labels"])
        except (json.JSONDecodeError, TypeError):
            d["labels"] = []
        out.append(InferenceOut(**d))
    return InferenceListOut(inferences=out, total=total)


@app.get("/summary")
def summary(
    date_from: str = Query(...),
    date_to: str = Query(...),
    bucket: str = Query("hour"),
    db: sqlite3.Connection = Depends(get_db),
):
    """Label-count aggregation over the inference history (layer 3). Buckets are
    system-local (TZ) hours or days; each bucket carries the label counts and
    the total inference count so the client can normalize by the total —
    inference cadence varies by device and preset, so raw counts alone would
    distort occupancy. Empty buckets inside the range are included as zeros."""
    if bucket not in ("hour", "day"):
        raise HTTPException(400, "bucket must be 'hour' or 'day'")
    date_from = _normalize_date_query("date_from", date_from)
    date_to = _normalize_date_query("date_to", date_to)
    lo = datetime.strptime(date_from, "%Y-%m-%d").astimezone()
    hi = datetime.strptime(date_to, "%Y-%m-%d").astimezone() + timedelta(days=1)
    if lo >= hi:
        raise HTTPException(400, "date_from must not be after date_to")

    rows = db.execute(
        "SELECT created_at, labels FROM inferences WHERE created_at >= ? AND created_at <= ?",
        (_local_date_bound_utc(date_from, end=False), _local_date_bound_utc(date_to, end=True)),
    ).fetchall()

    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
    buckets: dict[str, dict] = {}
    cur = lo
    while cur < hi:
        buckets[cur.isoformat()] = {"bucket_start": cur.isoformat(), "counts": {}, "total": 0}
        cur += step

    for r in rows:
        at = datetime.strptime(r["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).astimezone()
        start = at.replace(minute=0, second=0, microsecond=0)
        if bucket == "day":
            start = start.replace(hour=0)
        b = buckets.get(start.isoformat())
        if b is None:
            continue  # @claude Drop leftover rows outside the bounds (DST etc.).
        b["total"] += 1
        try:
            labels = json.loads(r["labels"])
        except (json.JSONDecodeError, TypeError):
            labels = []
        for label in labels:
            if isinstance(label, str):
                b["counts"][label] = b["counts"].get(label, 0) + 1

    return {"bucket": bucket, "buckets": list(buckets.values())}


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
    return {
        **_hw.snapshot(),
        **disk_usage(CLIP_DIR),
        **status.snapshot(),
        "clip_count": clip_count(),
        "event_count": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
    }

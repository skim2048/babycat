"""Babycat API Server — clips, events, devices."""

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from database import DB_PATH, get_db, init_db
from schemas import (
    ClipDeleteIn,
    ClipListOut,
    ClipOut,
    DeletedOut,
    DeviceIn,
    DeviceListOut,
    DeviceOut,
    EventIn,
    EventListOut,
    EventOut,
)

CLIP_DIR = os.environ.get("CLIP_DIR", "/data/clips")
MIN_CLIP_SIZE = 10240  # 10KB — ffmpeg 녹화 중 불완전 파일 제외


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Babycat API", version="0.1.0", lifespan=lifespan)


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Clips ────────────────────────────────────────────────────────────────────


def _list_clips(q: str | None = None) -> list[ClipOut]:
    d = Path(CLIP_DIR)
    if not d.exists():
        return []
    files = sorted(d.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    clips = []
    for f in files:
        stat = f.stat()
        if stat.st_size < MIN_CLIP_SIZE:
            continue
        if q and q.lower() not in f.name.lower():
            continue
        clips.append(ClipOut(
            name=f.name,
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
    return clips


def _validate_clip_name(name: str) -> Path:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "invalid clip name")
    fpath = Path(CLIP_DIR) / name
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(404, "clip not found")
    return fpath


@app.get("/clips", response_model=ClipListOut)
def list_clips(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
):
    all_clips = _list_clips(q)
    return ClipListOut(clips=all_clips[offset:offset + limit], total=len(all_clips))


@app.get("/clips/{name}")
def get_clip(name: str, request: Request):
    fpath = _validate_clip_name(name)
    file_size = fpath.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(fpath, media_type="video/mp4")

    m = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not m:
        raise HTTPException(416, "invalid range")

    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else file_size - 1
    end = min(end, file_size - 1)
    length = end - start + 1

    with open(fpath, "rb") as f:
        f.seek(start)
        data = f.read(length)

    return Response(
        content=data,
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
    deleted = 0
    for name in body.names:
        if "/" in name or "\\" in name or ".." in name:
            continue
        fpath = Path(CLIP_DIR) / name
        if fpath.exists() and fpath.is_file():
            fpath.unlink()
            deleted += 1
    return DeletedOut(deleted=deleted)


@app.delete("/clips/all", response_model=DeletedOut)
def delete_all_clips():
    d = Path(CLIP_DIR)
    if not d.exists():
        return DeletedOut(deleted=0)
    deleted = 0
    for f in d.glob("*.mp4"):
        f.unlink()
        deleted += 1
    return DeletedOut(deleted=deleted)


# ── Events ───────────────────────────────────────────────────────────────────


@app.get("/events", response_model=EventListOut)
def list_events(
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    rows = db.execute(
        "SELECT id, trigger, clip_name, created_at FROM events "
        "ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    events = [EventOut(**dict(r)) for r in rows]
    return EventListOut(events=events, total=total)


@app.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO events (trigger, clip_name) VALUES (?, ?)",
        (body.trigger, body.clip_name),
    )
    db.commit()
    row = db.execute(
        "SELECT id, trigger, clip_name, created_at FROM events WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return EventOut(**dict(row))


@app.delete("/events", response_model=DeletedOut)
def delete_events(db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM events")
    db.commit()
    return DeletedOut(deleted=cur.rowcount)


# ── Devices ──────────────────────────────────────────────────────────────────


@app.get("/devices", response_model=DeviceListOut)
def list_devices(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT id, fcm_token, label, registered_at FROM devices ORDER BY id"
    ).fetchall()
    devices = [DeviceOut(**dict(r)) for r in rows]
    return DeviceListOut(devices=devices)


@app.post("/devices", response_model=DeviceOut)
def register_device(body: DeviceIn, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute(
        "SELECT id FROM devices WHERE fcm_token = ?", (body.fcm_token,)
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE devices SET label = ? WHERE id = ?",
            (body.label, existing["id"]),
        )
        db.commit()
        row = db.execute(
            "SELECT id, fcm_token, label, registered_at FROM devices WHERE id = ?",
            (existing["id"],),
        ).fetchone()
    else:
        cur = db.execute(
            "INSERT INTO devices (fcm_token, label) VALUES (?, ?)",
            (body.fcm_token, body.label),
        )
        db.commit()
        row = db.execute(
            "SELECT id, fcm_token, label, registered_at FROM devices WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()

    return DeviceOut(**dict(row))


@app.delete("/devices/{device_id}", response_model=DeletedOut)
def delete_device(device_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "device not found")
    return DeletedOut(deleted=1)

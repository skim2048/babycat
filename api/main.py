"""
Babycat API Server — clips, events, devices.

Clip Storage Architecture:
    클립은 카메라 이름별 디렉토리 계층으로 관리된다:
        {CAM_DIR}/{camera_name}/*.mp4

    각 카메라 이름은 사용자가 지정하며, 고유해야 한다.
    새 카메라가 설정되면 해당 이름의 디렉토리에 클립이 저장된다.
    이 API는 현재 카메라뿐 아니라 과거 카메라의 클립에도
    통합적으로 접근할 수 있는 인터페이스를 제공한다.
    'camera' 쿼리 파라미터로 특정 카메라의 클립만 필터링할 수 있다.
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from database import DB_PATH, get_db, init_db
from schemas import (
    CameraListOut,
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

CAM_DIR = os.environ.get("CAM_DIR", "/data/cam")
MIN_CLIP_SIZE = 10240  # 10KB — ffmpeg 녹화 중 불완전 파일 제외


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Babycat API", version="1.0.0", lifespan=lifespan)


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Cameras ──────────────────────────────────────────────────────────────────


@app.get("/cameras", response_model=CameraListOut)
def list_cameras():
    """클립 디렉토리가 존재하는 카메라 이름 목록을 반환한다."""
    base = Path(CAM_DIR)
    if not base.exists():
        return CameraListOut(cameras=[])
    cameras = sorted(d.name for d in base.iterdir() if d.is_dir())
    return CameraListOut(cameras=cameras)


# ── Clips ────────────────────────────────────────────────────────────────────


def _list_clips(q: str | None = None, camera: str | None = None) -> list[ClipOut]:
    """
    모든 카메라 디렉토리(또는 특정 카메라)에서 클립을 조회한다.

    Args:
        q: 파일명 검색 필터 (부분 일치).
        camera: 특정 카메라 이름 필터. None이면 전체 카메라 대상.
    """
    base = Path(CAM_DIR)
    if not base.exists():
        return []

    if camera:
        dirs = [base / camera]
    else:
        dirs = [d for d in base.iterdir() if d.is_dir()]

    entries = []
    for cam_dir in dirs:
        if not cam_dir.is_dir():
            continue
        cam_name = cam_dir.name
        for f in cam_dir.glob("*.mp4"):
            st = f.stat()
            if st.st_size >= MIN_CLIP_SIZE:
                entries.append((f.name, st.st_size, st.st_mtime, cam_name))

    entries.sort(key=lambda e: e[2], reverse=True)
    clips = []
    for name, size, mtime, cam_name in entries:
        if q and q.lower() not in name.lower():
            continue
        clips.append(ClipOut(
            name=name,
            size=size,
            camera=cam_name,
            created_at=datetime.fromtimestamp(mtime, tz=timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"),
        ))
    return clips


def _resolve_clip(name: str, camera: str | None = None) -> Path:
    """
    클립 파일 경로를 확인한다.
    camera가 지정되면 해당 디렉토리만, 아니면 전체 카메라 디렉토리를 탐색한다.
    """
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "invalid clip name")
    base = Path(CAM_DIR)
    if camera:
        fpath = base / camera / name
        if fpath.exists() and fpath.is_file():
            return fpath
    else:
        for cam_dir in base.iterdir():
            if cam_dir.is_dir():
                fpath = cam_dir / name
                if fpath.exists() and fpath.is_file():
                    return fpath
    raise HTTPException(404, "clip not found")


@app.get("/clips", response_model=ClipListOut)
def list_clips(
    q: str | None = Query(None),
    camera: str | None = Query(None),
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
):
    all_clips = _list_clips(q, camera)
    return ClipListOut(clips=all_clips[offset:offset + limit], total=len(all_clips))


@app.get("/clips/{name}")
def get_clip(name: str, request: Request, camera: str | None = Query(None)):
    fpath = _resolve_clip(name, camera)
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
    deleted = 0
    base = Path(CAM_DIR)
    for name in body.names:
        if "/" in name or "\\" in name or ".." in name:
            continue
        if body.camera:
            fpath = base / body.camera / name
            if fpath.exists() and fpath.is_file():
                fpath.unlink()
                deleted += 1
        else:
            # camera 미지정 시 전체 디렉토리 탐색
            for cam_dir in base.iterdir():
                if cam_dir.is_dir():
                    fpath = cam_dir / name
                    if fpath.exists() and fpath.is_file():
                        fpath.unlink()
                        deleted += 1
                        break
    return DeletedOut(deleted=deleted)


@app.delete("/clips/all", response_model=DeletedOut)
def delete_all_clips(camera: str | None = Query(None)):
    """전체 또는 특정 카메라의 클립을 모두 삭제한다."""
    base = Path(CAM_DIR)
    if not base.exists():
        return DeletedOut(deleted=0)

    if camera:
        dirs = [base / camera]
    else:
        dirs = [d for d in base.iterdir() if d.is_dir()]

    deleted = 0
    for cam_dir in dirs:
        if not cam_dir.is_dir():
            continue
        for f in cam_dir.glob("*.mp4"):
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
    row = db.execute(
        "SELECT id, trigger, clip_name, created_at FROM events WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return EventOut(**dict(row))


@app.delete("/events", response_model=DeletedOut)
def delete_events(db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM events")
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
        row = db.execute(
            "SELECT id, fcm_token, label, registered_at FROM devices WHERE id = ?",
            (existing["id"],),
        ).fetchone()
    else:
        cur = db.execute(
            "INSERT INTO devices (fcm_token, label) VALUES (?, ?)",
            (body.fcm_token, body.label),
        )
        row = db.execute(
            "SELECT id, fcm_token, label, registered_at FROM devices WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()

    return DeviceOut(**dict(row))


@app.delete("/devices/{device_id}", response_model=DeletedOut)
def delete_device(device_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "device not found")
    return DeletedOut(deleted=1)

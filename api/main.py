"""
Babycat API server — clips, events, devices.

Clip storage architecture:
    Single-camera assumption. The app container's save_trigger_clip
    writes files (via ffmpeg re-recording from RTSP) to:
        {CAM_DIR}/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4

    This API mounts the same volume for listing, playback, and deletion.
    Listing uses rglob across the year/month tree. Name resolution first
    tries the direct {CAM_DIR}/YYYY/MM/{name} path inferred from the
    filename's leading YYYYMMDD, then falls back to rglob.

@claude
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from auth import (
    JWT_EXPIRY,
    REFRESH_EXPIRY,
    authenticate,
    change_password,
    create_token,
    init_users,
    require_auth,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app_proxy import (
    camera_apply_out,
    camera_profile_out,
    proxy_app,
    request_auth_header,
)
from database import DB_PATH, get_db, init_db
from clip_support import parse_byte_range, resolve_clip_path
from schemas import (
    ApplyResultOut,
    CameraProfileIn,
    CameraProfileOut,
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
    ChangePasswordIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    RefreshOut,
    TokenOut,
)
import json

APP_INTERNAL_URL = os.environ.get("BABYCAT_APP_URL", "http://babycat-app:8080")

CAM_DIR = os.environ.get("CAM_DIR", "/data")
MIN_CLIP_SIZE = 10240  # @claude 10KB — excludes partially-written files from an in-progress ffmpeg recording.


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # @claude Initialize the users table and seed the default account.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init_users(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Babycat API", version="1.0.0", lifespan=lifespan)

# @claude CORS — allow local development and private-network origins.
# @claude Matches localhost/127.0.0.1, private IP ranges (10.*, 172.16-31.*, 192.168.*),
# @claude and the Capacitor origin via regex.
# @claude For production / external domains, add CORS_EXTRA_ORIGINS=https://a.com,https://b.com.
_extra = [o.strip() for o in os.environ.get("CORS_EXTRA_ORIGINS", "").split(",") if o.strip()]
_origin_regex = (
    r"^(https?://(localhost|127\.0\.0\.1|"
    r"10(\.\d{1,3}){3}|"
    r"172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2}|"
    r"192\.168(\.\d{1,3}){2})"
    r"(:\d+)?|capacitor://localhost)$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_extra,
    allow_origin_regex=_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ─────────────────────────────────────────────────────────────────────


@app.post("/api/login", response_model=TokenOut)
def login(body: LoginIn, db: sqlite3.Connection = Depends(get_db)):
    result = authenticate(body.username, body.password, db, remember_me=body.remember_me)
    if not result:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return _token_out(result)


@app.post("/api/refresh", response_model=RefreshOut)
def refresh(body: RefreshIn, db: sqlite3.Connection = Depends(get_db)):
    rotated = rotate_refresh_token(body.refresh_token, db)
    if not rotated:
        raise HTTPException(status_code=401, detail="invalid or expired refresh token")
    username, new_refresh_token = rotated
    return _refresh_out(username, new_refresh_token)


@app.post("/api/logout")
def logout(body: LogoutIn, db: sqlite3.Connection = Depends(get_db)):
    """Revoke the refresh token. Access-token validation is skipped because it may already be lost. @claude"""
    if body.refresh_token:
        revoke_refresh_token(body.refresh_token, db)
    return {"ok": True}


@app.post("/api/change-password")
def api_change_password(
    body: ChangePasswordIn,
    user: dict = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    ok = change_password(user["sub"], body.current_password, body.new_password, db)
    if not ok:
        raise HTTPException(status_code=400, detail="current password is incorrect")
    return {"ok": True}


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Camera profile (proxied to babycat-app) ──────────────────────────────────


def _token_out(result: dict) -> TokenOut:
    """Normalize the login result into the client-facing token contract. @codex"""
    return TokenOut(
        token=result["token"],
        expires_in=JWT_EXPIRY,
        must_change_password=result["must_change_password"],
        refresh_token=result["refresh_token"],
        refresh_expires_in=REFRESH_EXPIRY if result["refresh_token"] else None,
    )


def _refresh_out(username: str, refresh_token: str) -> RefreshOut:
    """Normalize the refresh flow into the client-facing refresh contract. @codex"""
    return RefreshOut(
        token=create_token(username),
        expires_in=JWT_EXPIRY,
        refresh_token=refresh_token,
        refresh_expires_in=REFRESH_EXPIRY,
    )


@app.get("/camera", response_model=CameraProfileOut)
def get_camera(request: Request, _=Depends(require_auth)):
    """Return the current camera profile; configured=False when unset. @claude"""
    _, data = proxy_app(APP_INTERNAL_URL, "GET", "/camera", request_auth_header(request))
    return camera_profile_out(data)


@app.post("/camera", response_model=ApplyResultOut)
def set_camera(request: Request, body: CameraProfileIn, _=Depends(require_auth)):
    """Apply a camera profile; babycat-app persists it and restarts the pipeline. @claude"""
    payload = body.model_dump()
    status, data = proxy_app(APP_INTERNAL_URL, "POST", "/camera", request_auth_header(request), payload)
    return camera_apply_out(status, data)


# ── Clips ────────────────────────────────────────────────────────────────────


def _read_clip_meta(mp4_path: Path) -> dict:
    """Read the same-name .json metadata (trigger event info). Returns an empty dict when missing. @claude"""
    meta_path = mp4_path.with_suffix(".json")
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _list_clips(q: str | None = None) -> list[ClipOut]:
    """Recursively scan {CAM_DIR}/{YYYY}/{MM}/*.mp4 and return the clip list.
    If a same-name .json metadata file exists, its timestamp/keywords/vlm_text
    fields are populated on the result.

    @claude
    """
    base = Path(CAM_DIR)
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
        if q and q.lower() not in fpath.name.lower():
            continue
        meta = _read_clip_meta(fpath)
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


def _resolve_clip(name: str) -> Path:
    """Extract YYYYMMDD from the name -> {CAM_DIR}/YYYY/MM/{name}. Falls back to rglob. @claude"""
    base = Path(CAM_DIR)
    resolved = resolve_clip_path(base, name)
    if resolved is None and any(sep in name for sep in ("/", "\\", "..")):
        raise HTTPException(400, "invalid clip name")
    if resolved is not None:
        return resolved
    raise HTTPException(404, "clip not found")


@app.get("/clips", response_model=ClipListOut)
def list_clips(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    _=Depends(require_auth),
):
    all_clips = _list_clips(q)
    return ClipListOut(clips=all_clips[offset:offset + limit], total=len(all_clips))


@app.get("/clips/{name}")
def get_clip(name: str, request: Request, _=Depends(require_auth)):
    fpath = _resolve_clip(name)
    file_size = fpath.stat().st_size
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(fpath, media_type="video/mp4")

    byte_range = parse_byte_range(range_header, file_size)
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
def delete_clips(body: ClipDeleteIn, _=Depends(require_auth)):
    """Delete clips matching the given name list; uses the same path inference as _resolve_clip. @claude"""
    deleted = 0
    base = Path(CAM_DIR)
    for name in body.names:
        fpath = resolve_clip_path(base, name)
        if fpath is not None:
            fpath.unlink()
            meta_path = fpath.with_suffix(".json")
            if meta_path.exists():
                meta_path.unlink()
            deleted += 1
    return DeletedOut(deleted=deleted)


@app.delete("/clips/all", response_model=DeletedOut)
def delete_all_clips(_=Depends(require_auth)):
    """Delete every mp4 clip and its matching .json metadata under the {CAM_DIR} tree. @claude"""
    base = Path(CAM_DIR)
    if not base.exists():
        return DeletedOut(deleted=0)

    deleted = 0
    for f in base.rglob("*.mp4"):
        if not f.is_file():
            continue
        f.unlink()
        meta_path = f.with_suffix(".json")
        if meta_path.exists():
            meta_path.unlink()
        deleted += 1
    return DeletedOut(deleted=deleted)


# ── Events ───────────────────────────────────────────────────────────────────


@app.get("/events", response_model=EventListOut)
def list_events(
    limit: int = Query(50, ge=1),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
    _=Depends(require_auth),
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
def create_event(body: EventIn, db: sqlite3.Connection = Depends(get_db), _=Depends(require_auth)):
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
def delete_events(db: sqlite3.Connection = Depends(get_db), _=Depends(require_auth)):
    cur = db.execute("DELETE FROM events")
    return DeletedOut(deleted=cur.rowcount)


# ── Devices ──────────────────────────────────────────────────────────────────


@app.get("/devices", response_model=DeviceListOut)
def list_devices(db: sqlite3.Connection = Depends(get_db), _=Depends(require_auth)):
    rows = db.execute(
        "SELECT id, fcm_token, label, registered_at FROM devices ORDER BY id"
    ).fetchall()
    devices = [DeviceOut(**dict(r)) for r in rows]
    return DeviceListOut(devices=devices)


@app.post("/devices", response_model=DeviceOut)
def register_device(body: DeviceIn, db: sqlite3.Connection = Depends(get_db), _=Depends(require_auth)):
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
def delete_device(device_id: int, db: sqlite3.Connection = Depends(get_db), _=Depends(require_auth)):
    cur = db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "device not found")
    return DeletedOut(deleted=1)

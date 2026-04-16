"""
Babycat API Server — clips, events, devices.

Clip Storage Architecture:
    단일 카메라 전제. app 컨테이너의 save_trigger_clip이 ffmpeg로 RTSP에서 직접
    재녹화하여 다음 경로에 저장한다:
        {CAM_DIR}/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4

    이 API는 동일 볼륨을 읽어 클립 목록·재생·삭제를 제공한다. 조회는 rglob으로
    연/월 트리를 재귀 스캔한다. 파일 해석은 파일명에서 YYYYMMDD를 추출해
    {CAM_DIR}/YYYY/MM/{name} 경로를 직접 시도하고, 매칭이 없으면 rglob 폴백.
"""

import os
import re
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
    consume_refresh_token,
    create_token,
    init_users,
    require_auth,
    revoke_refresh_token,
)
from database import DB_PATH, get_db, init_db
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
import urllib.error
import urllib.request

APP_INTERNAL_URL = os.environ.get("BABYCAT_APP_URL", "http://babycat-app:8080")

CAM_DIR = os.environ.get("CAM_DIR", "/data")
MIN_CLIP_SIZE = 10240  # 10KB — ffmpeg 녹화 중 불완전 파일 제외


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # users 테이블 초기화 및 기본 계정 시딩
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init_users(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Babycat API", version="1.0.0", lifespan=lifespan)

# CORS — 로컬 개발 및 사설망 origin 허용.
# localhost/127.0.0.1, 사설 IP 대역(10.*, 172.16-31.*, 192.168.*), Capacitor origin을 regex로 매칭.
# 운영/외부 도메인은 환경변수 CORS_EXTRA_ORIGINS=https://a.com,https://b.com 로 추가.
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
    return TokenOut(
        token=result["token"],
        expires_in=JWT_EXPIRY,
        must_change_password=result["must_change_password"],
        refresh_token=result["refresh_token"],
        refresh_expires_in=REFRESH_EXPIRY if result["refresh_token"] else None,
    )


@app.post("/api/refresh", response_model=RefreshOut)
def refresh(body: RefreshIn, db: sqlite3.Connection = Depends(get_db)):
    username = consume_refresh_token(body.refresh_token, db)
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired refresh token")
    return RefreshOut(token=create_token(username), expires_in=JWT_EXPIRY)


@app.post("/api/logout")
def logout(body: LogoutIn, db: sqlite3.Connection = Depends(get_db)):
    """refresh token을 폐기. access token 검증 불필요 (이미 분실 가능성)."""
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


# ── Camera Profile (babycat-app 으로 프록시) ─────────────────────────────────


def _proxy_app(method: str, path: str, auth_header: str | None, body: dict | None = None, timeout: int = 10):
    """babycat-app 내부 디버그 서버로 프록시. (status, json) 반환."""
    url = f"{APP_INTERNAL_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if auth_header:
        req.add_header("Authorization", auth_header)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        return e.code, (json.loads(text) if text else None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")


@app.get("/camera", response_model=CameraProfileOut)
def get_camera(request: Request, _=Depends(require_auth)):
    """현재 카메라 프로필 조회. configured=False면 미설정 상태."""
    auth = request.headers.get("Authorization")
    _, data = _proxy_app("GET", "/camera", auth)
    return CameraProfileOut(**(data or {"configured": False}))


@app.post("/camera", response_model=ApplyResultOut)
def set_camera(request: Request, body: CameraProfileIn, _=Depends(require_auth)):
    """카메라 프로필 적용. babycat-app 측에서 저장 + 파이프라인 재시작."""
    auth = request.headers.get("Authorization")
    payload = body.model_dump(exclude_none=True)
    status, data = _proxy_app("POST", "/camera", auth, payload)
    if status >= 500:
        raise HTTPException(status_code=502, detail="upstream error")
    return ApplyResultOut(**(data or {"ok": False, "error": "no response"}))


# ── Clips ────────────────────────────────────────────────────────────────────


def _read_clip_meta(mp4_path: Path) -> dict:
    """동명의 .json 메타데이터(트리거 이벤트 정보)를 읽어 반환. 없으면 빈 dict."""
    meta_path = mp4_path.with_suffix(".json")
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _list_clips(q: str | None = None) -> list[ClipOut]:
    """{CAM_DIR}/{YYYY}/{MM}/*.mp4 트리를 재귀 스캔하여 클립 목록을 반환한다.

    동명의 .json 메타데이터가 있으면 timestamp/keywords/vlm_text 필드를 채운다.
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
    """파일명에서 YYYYMMDD 추출 → {CAM_DIR}/YYYY/MM/{name}. 폴백은 rglob."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "invalid clip name")
    base = Path(CAM_DIR)
    if len(name) >= 8 and name[:8].isdigit():
        candidate = base / name[:4] / name[4:6] / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for p in base.rglob(name):
        if p.is_file():
            return p
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
def delete_clips(body: ClipDeleteIn, _=Depends(require_auth)):
    """이름 목록에 매칭되는 클립을 삭제. _resolve_clip과 동일한 경로 추론을 사용한다."""
    deleted = 0
    base = Path(CAM_DIR)
    for name in body.names:
        if "/" in name or "\\" in name or ".." in name:
            continue
        fpath: Path | None = None
        if len(name) >= 8 and name[:8].isdigit():
            candidate = base / name[:4] / name[4:6] / name
            if candidate.exists() and candidate.is_file():
                fpath = candidate
        if fpath is None:
            for p in base.rglob(name):
                if p.is_file():
                    fpath = p
                    break
        if fpath is not None:
            fpath.unlink()
            meta_path = fpath.with_suffix(".json")
            if meta_path.exists():
                meta_path.unlink()
            deleted += 1
    return DeletedOut(deleted=deleted)


@app.delete("/clips/all", response_model=DeletedOut)
def delete_all_clips(_=Depends(require_auth)):
    """{CAM_DIR} 트리의 모든 mp4 클립과 동명의 메타데이터(.json)를 삭제."""
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

"""
Babycat router — single external entry point (SDD §4.1).

Owns the accounts: credentials, tokens, and per-request authentication
all live in this process, so the revocation (epoch) check is a local
database read. Everything else is relayed to the owning component —
profile/PTZ to the streamer's companion process, analysis to the
analyzer, clips/history to the recorder — plus the HLS/WHEP relays
(single-entry decision, SDD §2.4 (2)) and the monitoring synthesis.

@claude
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.request
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import monitor
from auth import (
    JWT_EXPIRY,
    REFRESH_EXPIRY,
    SESSION_LOCK,
    authenticate,
    bump_epoch,
    change_password,
    create_token,
    get_epoch,
    require_auth,
    revoke_refresh_token,
    rotate_refresh_token,
    seed_default_user,
    verify_token,
)
from database import DB_PATH, get_db, init_db
from proxy import forward_json, relay_raw, relay_stream

STREAMER_URL = os.environ.get("STREAMER_URL", "http://streamer:8080")
ANALYZER_URL = os.environ.get("ANALYZER_URL", "http://analyzer:8080")
RECORDER_URL = os.environ.get("RECORDER_URL", "http://recorder:8080")
STREAMER_HLS_URL = os.environ.get("STREAMER_HLS_URL", "http://streamer:8888")
STREAMER_WEBRTC_URL = os.environ.get("STREAMER_WEBRTC_URL", "http://streamer:8889")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        seed_default_user(conn)
    finally:
        conn.close()
    monitor.start_collectors()
    yield


app = FastAPI(title="Babycat router", version="1.0.0", lifespan=lifespan)

# @claude CORS — allow local development and private-network origins.
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


# @claude Access-log token masking (SDD §8.4): the ?token= fallback (§6.2)
# @claude puts valid access tokens in request lines, and streaming endpoints
# @claude log them continuously — a copied or shared log must not carry live
# @claude credentials. Masking every string arg keeps this robust against
# @claude uvicorn changing its access-log arg layout.
_TOKEN_QUERY_RE = re.compile(r"(token=)[^&\s\"]+")


class _MaskTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _TOKEN_QUERY_RE.sub(r"\1***", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


logging.getLogger("uvicorn.access").addFilter(_MaskTokenFilter())


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Session replacement (FR-047) ─────────────────────────────────────────────
# @claude One login per account: a new login (or logout / password change)
# @claude bumps the account epoch. The replaced session's live streams are
# @claude closed too — relayed streams (SSE, MJPEG) stop via an epoch guard,
# @claude WHEP sessions (media bypasses the router) via an explicit DELETE.


def _current_epoch(username: str) -> int | None:
    # @claude Fresh short-lived connection: the guard runs on relay threads,
    # @claude outliving the request-scoped get_db connection.
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT token_epoch FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _epoch_guarded(inner, username: str, epoch: int, interval: float = 2.0):
    """Yield from inner until the account epoch moves past the session's."""
    last_check = time.monotonic()
    try:
        for chunk in inner:
            now = time.monotonic()
            if now - last_check >= interval:
                last_check = now
                if _current_epoch(username) != epoch:
                    break
            yield chunk
    finally:
        close = getattr(inner, "close", None)
        if close is not None:
            close()


# @claude The registry lives in the router DB (SDD §5.2): WebRTC media never
# @claude re-authenticates after setup, so a replacement must stay able to
# @claude close sessions registered before a router restart.
_whep_lock = threading.Lock()


def _whep_db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _register_whep_session(username: str, session_path: str) -> None:
    with _whep_lock:
        conn = _whep_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO whep_sessions (session_path, username) VALUES (?, ?)",
                (session_path, username),
            )
            conn.commit()
        finally:
            conn.close()


def _unregister_whep_session(username: str, session_path: str) -> None:
    with _whep_lock:
        conn = _whep_db()
        try:
            conn.execute(
                "DELETE FROM whep_sessions WHERE session_path = ? AND username = ?",
                (session_path, username),
            )
            conn.commit()
        finally:
            conn.close()


def _register_whep_and_recheck(username: str, epoch: int, session_path: str) -> None:
    _register_whep_session(username, session_path)
    # @claude FR-047 residual window: a replacement that swept this account's
    # @claude sessions while the setup was in flight missed this one — close
    # @claude it now instead of leaking it until the next session event.
    if _current_epoch(username) != epoch:
        _terminate_whep_sessions(username)


def _terminate_whep_sessions(username: str) -> None:
    with _whep_lock:
        conn = _whep_db()
        try:
            rows = conn.execute(
                "SELECT session_path FROM whep_sessions WHERE username = ?", (username,)
            ).fetchall()
            conn.execute("DELETE FROM whep_sessions WHERE username = ?", (username,))
            conn.commit()
        finally:
            conn.close()
        sessions = [row[0] for row in rows]
    for session_path in sessions:
        try:
            req = urllib.request.Request(
                f"{STREAMER_WEBRTC_URL}{session_path}", method="DELETE"
            )
            urllib.request.urlopen(req, timeout=5).close()
        except Exception:
            pass  # @claude Already gone (client DELETE or ICE timeout).


# ── Accounts and tokens (owned, SDD §6.2) ────────────────────────────────────


class LoginIn(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class TokenOut(BaseModel):
    token: str
    expires_in: int
    must_change_password: bool = False
    refresh_token: Optional[str] = None
    refresh_expires_in: Optional[int] = None


class RefreshIn(BaseModel):
    refresh_token: str


class RefreshOut(BaseModel):
    token: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


class LogoutIn(BaseModel):
    refresh_token: Optional[str] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/login", response_model=TokenOut)
def login(body: LoginIn, db: sqlite3.Connection = Depends(get_db)):
    result = authenticate(body.username, body.password, db, remember_me=body.remember_me)
    if not result:
        raise HTTPException(status_code=401, detail="invalid credentials")
    # @claude FR-047: the replaced session's streams die with its tokens.
    _terminate_whep_sessions(body.username)
    return TokenOut(
        token=result["token"],
        expires_in=JWT_EXPIRY,
        must_change_password=result["must_change_password"],
        refresh_token=result["refresh_token"],
        refresh_expires_in=REFRESH_EXPIRY if result["refresh_token"] else None,
    )


@app.post("/api/refresh", response_model=RefreshOut)
def refresh(body: RefreshIn, db: sqlite3.Connection = Depends(get_db)):
    # @claude Rotation and access-token minting share one critical section:
    # @claude interleaved with a login replacement, the rotated pair could
    # @claude otherwise outlive the replacement (FR-047, SDD §6.2).
    with SESSION_LOCK:
        rotated = rotate_refresh_token(body.refresh_token, db)
        if not rotated:
            raise HTTPException(status_code=401, detail="invalid or expired refresh token")
        username, new_refresh_token = rotated
        token = create_token(username, get_epoch(username, db) or 0)
    return RefreshOut(
        token=token,
        expires_in=JWT_EXPIRY,
        refresh_token=new_refresh_token,
        refresh_expires_in=REFRESH_EXPIRY,
    )


@app.post("/api/logout")
def logout(body: LogoutIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    """No auth requirement (the access token may already be lost). The epoch
    bump revokes outstanding access tokens (FR-003); the username comes from
    the refresh token when present, else from a still-current access token.
    Credentials of a replaced session identify no one — their logout must not
    bump the epoch again and kill the replacing session (FR-047)."""
    username = None
    with SESSION_LOCK:
        if body.refresh_token:
            username = revoke_refresh_token(body.refresh_token, db)
        if not username:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                claims = verify_token(auth_header[7:])
                # @claude Stale-epoch tokens are a replaced session's leftovers.
                if claims and claims.get("epoch", -1) == get_epoch(claims.get("sub", ""), db):
                    username = claims.get("sub")
        if username:
            bump_epoch(username, db)
    if username:
        _terminate_whep_sessions(username)
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
    _terminate_whep_sessions(user["sub"])
    return {"ok": True}


# ── Pet profile (router-owned) ────────────────────────────────────────────────
# @claude The pet profile lives here with the accounts: the client used to keep
# @claude it in localStorage only, which a reinstall or another device loses.
# @claude Named /pet/profile because plain /profile already means the video
# @claude source profile on the streamer side (relayed via /camera).


class PetProfileIn(BaseModel):
    name: str = Field("", max_length=100)
    breed: str = Field("", max_length=100)
    birth: str = Field("", max_length=10)  # ISO date (YYYY-MM-DD) or empty
    # @claude Client-side downscaled JPEG data URL (512px square). The cap
    # @claude bounds the row size; a compliant client stays well under it.
    photo: str = Field("", max_length=300_000)
    notes: str = Field("", max_length=2_000)


@app.get("/pet/profile")
def get_pet_profile(
    user: dict = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        "SELECT data FROM profiles WHERE username = ?", (user["sub"],)
    ).fetchone()
    stored = {}
    if row:
        try:
            stored = json.loads(row["data"])
        except ValueError:
            pass  # @claude Corrupted row: served empty, replaced on next save.
    return {**PetProfileIn().model_dump(), **stored}


@app.put("/pet/profile")
def put_pet_profile(
    body: PetProfileIn,
    user: dict = Depends(require_auth),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute(
        """INSERT INTO profiles (username, data, updated_at)
           VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
           ON CONFLICT(username) DO UPDATE
           SET data = excluded.data, updated_at = excluded.updated_at""",
        (user["sub"], json.dumps(body.model_dump(), ensure_ascii=False)),
    )
    return {"ok": True}


# ── Video source profile / PTZ (streamer companion) ──────────────────────────


@app.get("/camera")
def get_camera(_=Depends(require_auth)):
    return forward_json(STREAMER_URL, "GET", "/profile")


@app.post("/camera")
def set_camera(payload: dict, _=Depends(require_auth)):
    return forward_json(STREAMER_URL, "POST", "/profile", payload)


@app.post("/ptz")
def control_ptz(payload: dict, _=Depends(require_auth)):
    return forward_json(STREAMER_URL, "POST", "/ptz", payload)


# ── Scene analysis (analyzer + fan-out) ──────────────────────────────────────


@app.post("/prompt")
def set_prompt(payload: dict, _=Depends(require_auth)):
    return forward_json(ANALYZER_URL, "POST", "/prompt", payload)


@app.post("/presets")
def set_presets(payload: dict, _=Depends(require_auth)):
    """Relay the label vocabulary / time-ranged presets to the analyzer (2층)."""
    return forward_json(ANALYZER_URL, "POST", "/presets", payload)


@app.post("/vlm/switch")
def switch_vlm(payload: dict, _=Depends(require_auth)):
    return forward_json(ANALYZER_URL, "POST", "/vlm/switch", payload)


def _fan_out(targets: tuple) -> tuple[dict, list]:
    """POST to each internal target; collect status codes and failures.
    A leg fails on transport error, an error status, or a body that reports
    ok=false — the streamer reports an unapplied source detach that way, and
    hiding it would defeat the re-request repair (SDD §6.1)."""
    results = {}
    failures = []
    for name, base, path in targets:
        try:
            response = forward_json(base, "POST", path, {})
            results[name] = response.status_code
            body = json.loads(response.body) if response.body else None
            ok = body.get("ok", True) if isinstance(body, dict) else True
            if response.status_code >= 400 or not ok:
                failures.append(name)
        except Exception:
            results[name] = 502
            failures.append(name)
    return results, failures


def _streaming_active() -> bool | None:
    """Ask the streamer whether live streaming is active (FR-050 precheck).
    None when the streamer cannot be reached — an unreachable streamer must
    surface as 502, not masquerade as "not active" (SDD §6.5)."""
    try:
        with urllib.request.urlopen(f"{STREAMER_URL}/status", timeout=5) as resp:
            return bool(json.loads(resp.read().decode()).get("streaming_active"))
    except Exception:
        return None


# ── Live streaming lifecycle ─────────────────────────────────────────────────


@app.post("/streaming/start")
def streaming_start(_=Depends(require_auth)):
    """SRS §2.3 (3): promote the registered profile and connect the source
    (FR-048). Idempotent; doubles as a restart."""
    return forward_json(STREAMER_URL, "POST", "/streaming/start", {})


@app.post("/streaming/stop")
def streaming_stop(_=Depends(require_auth)):
    """SRS §2.3 (3): detach the source and cascade-stop analysis and
    buffering (FR-049)."""
    results, failures = _fan_out((
        ("streamer", STREAMER_URL, "/streaming/stop"),
        ("analyzer", ANALYZER_URL, "/stop"),
        ("recorder", RECORDER_URL, "/buffer/stop"),
    ))
    if failures:
        raise HTTPException(status_code=502, detail=f"stop not accepted by: {', '.join(failures)}")
    return {"ok": True, "accepted": results}


@app.post("/analysis/start")
def analysis_start(_=Depends(require_auth)):
    """
    SRS §2.3 (5): deliver the start request to the analyzer and the
    recorder. Requires live streaming to be active (FR-050). Idempotent;
    a partial failure is reported and repaired by re-requesting (SDD §6.1).
    """
    active = _streaming_active()
    if active is None:
        raise HTTPException(status_code=502, detail="cannot verify streaming state")
    if not active:
        raise HTTPException(status_code=409, detail="live streaming is not active")
    results, failures = _fan_out((
        ("analyzer", ANALYZER_URL, "/start"),
        ("recorder", RECORDER_URL, "/buffer/start"),
    ))
    if failures:
        raise HTTPException(status_code=502, detail=f"start not accepted by: {', '.join(failures)}")
    return {"ok": True, "accepted": results}


@app.post("/analysis/stop")
def analysis_stop(_=Depends(require_auth)):
    """SRS §2.3 (5): stop analysis and buffering while streaming stays up
    (FR-051). Idempotent."""
    results, failures = _fan_out((
        ("analyzer", ANALYZER_URL, "/stop"),
        ("recorder", RECORDER_URL, "/buffer/stop"),
    ))
    if failures:
        raise HTTPException(status_code=502, detail=f"stop not accepted by: {', '.join(failures)}")
    return {"ok": True, "accepted": results}


# ── Monitoring ───────────────────────────────────────────────────────────────


@app.get("/state")
def state_stream(user: dict = Depends(require_auth)):
    """Merged monitoring SSE (FR-042, FR-043; SDD §6.4 (4)). The relay ends
    when the session is replaced (FR-047)."""
    return StreamingResponse(
        _epoch_guarded(monitor.sse_generator(), user["sub"], user["epoch"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stream")
def frame_stream(user: dict = Depends(require_auth)):
    """Relay the analyzer's MJPEG stream of the frames fed to the VLM (FR-044).
    The relay ends when the session is replaced (FR-047)."""
    username, epoch = user["sub"], user["epoch"]
    return relay_stream(
        ANALYZER_URL, "/stream",
        stop_when=lambda: _current_epoch(username) != epoch,
    )


# ── Clips / event history (recorder) ─────────────────────────────────────────


@app.get("/clips")
async def list_clips(request: Request, _=Depends(require_auth)):
    return await relay_raw(request, RECORDER_URL, "/clips")


@app.get("/clips/{name}")
async def get_clip(name: str, request: Request, _=Depends(require_auth)):
    return await relay_raw(request, RECORDER_URL, f"/clips/{name}", timeout=60)


@app.delete("/clips")
def delete_clips(payload: dict, _=Depends(require_auth)):
    return forward_json(RECORDER_URL, "DELETE", "/clips", payload)


@app.delete("/clips/all")
def delete_all_clips(_=Depends(require_auth)):
    return forward_json(RECORDER_URL, "DELETE", "/clips/all")


@app.get("/events")
async def list_events(request: Request, _=Depends(require_auth)):
    return await relay_raw(request, RECORDER_URL, "/events")


@app.get("/inferences")
async def list_inferences(request: Request, _=Depends(require_auth)):
    """Relay the inference history (2층 이력) from the recorder."""
    return await relay_raw(request, RECORDER_URL, "/inferences")


@app.get("/summary")
async def get_summary(request: Request, _=Depends(require_auth)):
    """Relay the inference-history aggregation (3층) from the recorder."""
    return await relay_raw(request, RECORDER_URL, "/summary")


@app.delete("/events/{event_id}")
def delete_event(event_id: int, _=Depends(require_auth)):
    return forward_json(RECORDER_URL, "DELETE", f"/events/{event_id}")


@app.delete("/events")
def delete_events(_=Depends(require_auth)):
    return forward_json(RECORDER_URL, "DELETE", "/events")


# ── Live streaming relay (single entry, SDD §2.4 (2), §6.4 (2)) ──────────────


@app.get("/live/hls/{path:path}")
async def hls_relay(path: str, request: Request, _=Depends(require_auth)):
    """HLS playlist/segment relay. MediaMTX playlists use relative URLs,
    so no body rewriting is needed."""
    return await relay_raw(request, STREAMER_HLS_URL, f"/live/{path}")


@app.post("/live/whep")
async def whep_open(request: Request, user: dict = Depends(require_auth)):
    """WHEP session setup. The upstream Location header is path-form and the
    router serves the same path shape, so it passes through unchanged. The
    session path is registered so replacement can close it (FR-047)."""
    response = await relay_raw(request, STREAMER_WEBRTC_URL, "/live/whep")
    if response.status_code == 201:
        location = response.headers.get("location")
        if location:
            # @claude Registry I/O blocks (DB writes; HTTP DELETEs in the race
            # @claude branch) — keep it off the event loop, like relay_raw does.
            await run_in_threadpool(
                _register_whep_and_recheck, user["sub"], user["epoch"], location
            )
    return response


@app.patch("/live/whep/{session:path}")
async def whep_patch(session: str, request: Request, _=Depends(require_auth)):
    return await relay_raw(request, STREAMER_WEBRTC_URL, f"/live/whep/{session}")


@app.delete("/live/whep/{session:path}")
async def whep_close(session: str, request: Request, user: dict = Depends(require_auth)):
    await run_in_threadpool(
        _unregister_whep_session, user["sub"], f"/live/whep/{session}"
    )
    return await relay_raw(request, STREAMER_WEBRTC_URL, f"/live/whep/{session}")

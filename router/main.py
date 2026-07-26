"""
Babycat router — single external entry point (SDD §4.1).

Authenticates every request in one place, relays control to the owning
component, relays HLS and WebRTC signaling to the streamer (single-entry
decision, SDD §2.4 (2)), and synthesizes the monitoring stream. Holds no
state of its own.

@claude
"""

import os

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import monitor
from auth import require_auth
from proxy import forward_json, relay_raw, relay_stream

MANAGER_URL = os.environ.get("MANAGER_URL", "http://manager:8100")
CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://controller:8200")
ANALYZER_URL = os.environ.get("ANALYZER_URL", "http://analyzer:8300")
RECORDER_URL = os.environ.get("RECORDER_URL", "http://recorder:8400")
STREAMER_HLS_URL = os.environ.get("STREAMER_HLS_URL", "http://streamer:8888")
STREAMER_WEBRTC_URL = os.environ.get("STREAMER_WEBRTC_URL", "http://streamer:8889")

app = FastAPI(title="Babycat router", version="1.0.0")

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


@app.on_event("startup")
def _start_monitor():
    monitor.start_collectors()


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Auth (relayed to the manager) ────────────────────────────────────────────


@app.post("/api/login")
def login(payload: dict):
    return forward_json(MANAGER_URL, "POST", "/internal/login", payload)


@app.post("/api/refresh")
def refresh(payload: dict):
    return forward_json(MANAGER_URL, "POST", "/internal/refresh", payload)


@app.post("/api/logout")
def logout(payload: dict, request: Request):
    """No auth requirement (the access token may already be lost), but when a
    valid one is present its username rides along so the manager can bump the
    epoch even without a refresh token (FR-003)."""
    from auth import verify_token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        claims = verify_token(auth_header[7:])
        if claims:
            payload.setdefault("username", claims.get("sub"))
    return forward_json(MANAGER_URL, "POST", "/internal/logout", payload)


@app.post("/api/change-password")
def change_password(payload: dict, user: dict = Depends(require_auth)):
    payload["username"] = user["sub"]
    return forward_json(MANAGER_URL, "POST", "/internal/change-password", payload)


# ── Video source profile / PTZ (controller) ──────────────────────────────────


@app.get("/camera")
def get_camera(_=Depends(require_auth)):
    return forward_json(CONTROLLER_URL, "GET", "/profile")


@app.post("/camera")
def set_camera(payload: dict, _=Depends(require_auth)):
    return forward_json(CONTROLLER_URL, "POST", "/profile", payload)


@app.post("/ptz")
def control_ptz(payload: dict, _=Depends(require_auth)):
    return forward_json(CONTROLLER_URL, "POST", "/ptz", payload)


# ── Scene analysis (analyzer + fan-out) ──────────────────────────────────────


@app.post("/prompt")
def set_prompt(payload: dict, _=Depends(require_auth)):
    return forward_json(ANALYZER_URL, "POST", "/prompt", payload)


@app.post("/vlm/switch")
def switch_vlm(payload: dict, _=Depends(require_auth)):
    return forward_json(ANALYZER_URL, "POST", "/vlm/switch", payload)


@app.post("/analysis/start")
def analysis_start(_=Depends(require_auth)):
    """
    SRS §2.3 (4): deliver the start request to the analyzer, the source
    controller, and the recorder. Idempotent; a partial failure is
    reported and repaired by re-requesting (SDD §6.1).
    """
    results = {}
    failures = []
    for name, base, path in (
        ("analyzer", ANALYZER_URL, "/start"),
        ("controller", CONTROLLER_URL, "/activate"),
        ("recorder", RECORDER_URL, "/buffer/start"),
    ):
        try:
            response = forward_json(base, "POST", path, {})
            results[name] = response.status_code
        except Exception:
            results[name] = 502
            failures.append(name)
    if failures:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"start not accepted by: {', '.join(failures)}")
    return {"ok": True, "accepted": results}


# ── Monitoring ───────────────────────────────────────────────────────────────


@app.get("/state")
def state_stream(_=Depends(require_auth)):
    """Merged monitoring SSE (FR-042, FR-043; SDD §6.4 (4))."""
    return StreamingResponse(
        monitor.sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stream")
def frame_stream(_=Depends(require_auth)):
    """Relay the analyzer's MJPEG stream of the frames fed to the VLM (FR-044)."""
    return relay_stream(ANALYZER_URL, "/stream")


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
async def whep_open(request: Request, _=Depends(require_auth)):
    """WHEP session setup. The upstream Location header is path-form and the
    router serves the same path shape, so it passes through unchanged."""
    return await relay_raw(request, STREAMER_WEBRTC_URL, "/live/whep")


@app.patch("/live/whep/{session:path}")
async def whep_patch(session: str, request: Request, _=Depends(require_auth)):
    return await relay_raw(request, STREAMER_WEBRTC_URL, f"/live/whep/{session}")


@app.delete("/live/whep/{session:path}")
async def whep_close(session: str, request: Request, _=Depends(require_auth)):
    return await relay_raw(request, STREAMER_WEBRTC_URL, f"/live/whep/{session}")

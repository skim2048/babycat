"""
Babycat streamer — companion process (SDD §4.2).

Parent of the container's two-process structure: supervises the MediaMTX
child (spawn, restart on abnormal exit, orderly shutdown) the same way the
analyzer supervises its VLM child, and owns everything about the video
source that MediaMTX cannot do itself — the profile, its application to
the control API on localhost, and ONVIF PTZ.

Threads: MediaMTX supervisor, start-up profile restore, PTZ position
polling, PTZ auto patrol (SDD §3.4).

Internal only: no HTTP port is published; the router is the sole caller
(SDD §6.3). MediaMTX's own ports stay container-internal except the
WebRTC media port published by compose.

@claude
"""

import logging
import signal
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import camera
import ptz

log = logging.getLogger(__name__)

# @claude Fixed by the image layout (docker/streamer/Dockerfile) and the
# @claude compose volume (SDD §8.1); not operator-tunable.
MEDIAMTX_BIN = "/usr/local/bin/mediamtx"
MEDIAMTX_CONF = "/config/mediamtx.yml"
# @claude A child that stayed up this long ran normally; the next crash starts
# @claude the restart backoff from the base again.
_STABLE_RUN_S = 60.0

_mtx_proc: subprocess.Popen | None = None
_mtx_lock = threading.Lock()
_shutting_down = threading.Event()


def _mediamtx_supervisor() -> None:
    """Keep the MediaMTX child alive; restart with backoff on abnormal exit. @claude"""
    global _mtx_proc
    backoff = 1.0
    while not _shutting_down.is_set():
        with _mtx_lock:
            _mtx_proc = subprocess.Popen([MEDIAMTX_BIN, MEDIAMTX_CONF])
        log.info("MediaMTX started (pid=%d)", _mtx_proc.pid)
        started = time.monotonic()
        code = _mtx_proc.wait()
        if _shutting_down.is_set():
            break
        if time.monotonic() - started > _STABLE_RUN_S:
            backoff = 1.0
        log.warning("MediaMTX exited (code=%s) — restarting in %.0fs", code, backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, 10.0)
        # @claude After a child restart the runtime source config is gone;
        # @claude re-apply the saved profile through the normal startup path.
        threading.Thread(target=camera.startup_apply, daemon=True).start()


def _stop_mediamtx() -> None:
    """Orderly shutdown of the child: SIGTERM, then SIGKILL after 10 s. @claude"""
    _shutting_down.set()
    with _mtx_lock:
        proc = _mtx_proc
    if proc is not None and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    camera.sweep_temp_files()
    applied = camera.load_applied()
    ptz.load_presets(applied.get("ptz_presets"))
    ptz.load_patrol(applied.get("ptz_patrol"))

    threading.Thread(target=_mediamtx_supervisor, daemon=True).start()
    # @claude Apply the saved profile with retries until MediaMTX is up (FR-015);
    # @claude an intra-container wait, resolved here and nowhere else (SDD §3.5).
    threading.Thread(target=camera.startup_apply, daemon=True).start()
    threading.Thread(target=ptz.poll_loop, daemon=True).start()
    threading.Thread(target=ptz.patrol_loop, daemon=True).start()
    yield
    _stop_mediamtx()


app = FastAPI(title="Babycat streamer companion", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_as_400(_request: Request, exc: RequestValidationError):
    """A malformed request is 400 (SDD §6.5), not FastAPI's default 422."""
    return JSONResponse(status_code=400, content={"detail": "invalid request body"})


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid request body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid request body")
    return body


def _result(outcome: dict, failure_status: int) -> dict:
    """Translate camera's {"ok", "error"} outcome into the HTTP contract
    (SDD §6.5): failures are 4xx/5xx with a detail, never a 200. @claude"""
    if outcome.get("ok"):
        return {"ok": True}
    raise HTTPException(status_code=failure_status, detail=outcome.get("error", "failed"))


@app.get("/profile")
def get_profile():
    """Return the profile with the password reduced to password_set (FR-013)."""
    return camera.profile_view()


@app.post("/profile")
async def register_profile(request: Request):
    """Persist a profile into the registered slot (FR-009, FR-010). Does not
    connect the source (FR-048) and does not start analysis (FR-025)."""
    return _result(camera.register(await _json_body(request)), 400)


@app.post("/streaming/start")
def streaming_start():
    """Promote the registered profile and connect the source (SRS §2.3 (3),
    FR-048). Idempotent; doubles as a restart. A missing or invalid
    registered profile is the caller's error (409); an unreachable MediaMTX
    control API is an upstream failure (502)."""
    outcome = camera.streaming_start()
    if outcome.get("ok"):
        return {"ok": True}
    status = 502 if outcome.get("error") == camera.MEDIAMTX_API_ERROR else 409
    raise HTTPException(status_code=status, detail=outcome.get("error", "failed"))


@app.post("/streaming/stop")
def streaming_stop():
    """Detach the source (SRS §2.3 (3), FR-049). The router cascades the
    analysis and buffer stops separately."""
    return _result(camera.streaming_stop(), 502)


@app.post("/ptz")
async def control_ptz(request: Request):
    """PTZ control (FR-016~FR-019, FR-052). The camera in use has no zoom;
    zoom is outside the product scope (SRS §2.4)."""
    body = await _json_body(request)
    action = body.get("action")

    if action == "move":
        try:
            pan = float(body.get("pan", 0))
            tilt = float(body.get("tilt", 0))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid pan/tilt values")
        ptz.set_moving(True)
        threading.Thread(target=ptz.move, args=(pan, tilt), daemon=True).start()
    elif action == "stop":
        ptz.set_moving(False)
        threading.Thread(target=ptz.stop, daemon=True).start()
    elif action == "save":
        try:
            slot = int(body.get("slot"))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid preset slot")
        presets = ptz.save_preset(slot)
        if presets is None:
            raise HTTPException(status_code=409, detail="current position unknown or invalid slot")
        camera.save_presets(presets)
    elif action == "goto":
        try:
            slot = int(body.get("slot"))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid preset slot")
        preset = ptz.get_preset(slot)
        if preset is None:
            raise HTTPException(status_code=404, detail="preset not saved")
        threading.Thread(
            target=ptz.absolute_move,
            args=(preset["pan"], preset["tilt"]),
            daemon=True,
        ).start()
    elif action == "absolute":
        # @claude FR-016: move to an arbitrary position in ONVIF normalized
        # @claude space. Values are clamped to [-1, 1].
        try:
            pan = max(-1.0, min(1.0, float(body.get("pan"))))
            tilt = max(-1.0, min(1.0, float(body.get("tilt"))))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid pan/tilt values")
        threading.Thread(target=ptz.absolute_move, args=(pan, tilt), daemon=True).start()
    elif action == "patrol":
        # @claude FR-052: enable/disable the preset patrol and set its interval.
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            raise HTTPException(status_code=400, detail="invalid patrol payload")
        interval = body.get("interval_s")
        if interval is not None:
            try:
                interval = int(interval)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="invalid patrol interval")
        patrol = ptz.set_patrol(enabled, interval)
        camera.save_patrol(patrol)
    else:
        raise HTTPException(status_code=400, detail="unknown action")

    return {"ok": True}


@app.get("/status")
def status():
    """PTZ position snapshot for the router's monitoring merge (SDD §6.4 (4))."""
    current = ptz.get_current()
    return {
        "ptz_pan": current["pan"],
        "ptz_tilt": current["tilt"],
        "ptz_presets": sorted(ptz.get_presets()),  # @claude Saved slot numbers (FR-018).
        **camera.status_view(),
    }

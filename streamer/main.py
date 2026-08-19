"""
Babycat streamer — companion process (SDD §4.2).

Parent of the container's two-process structure: supervises the MediaMTX
child (spawn, restart on abnormal exit, signal forwarding) the same way
the analyzer supervises its VLM child and the recorder its ffmpeg
children, and owns everything about the video source that MediaMTX
cannot do itself — the profile, its application to the control API on
localhost, and ONVIF PTZ.

Internal only: no HTTP port is published; the router is the sole caller
(SDD §6.3). MediaMTX's own ports stay container-internal except the
WebRTC media port published by compose.

@claude
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

import camera
import ptz

log = logging.getLogger(__name__)

MEDIAMTX_BIN = os.getenv("MEDIAMTX_BIN", "/usr/local/bin/mediamtx")
MEDIAMTX_CONF = os.getenv("MEDIAMTX_CONF", "/config/mediamtx.yml")

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
        code = _mtx_proc.wait()
        if _shutting_down.is_set():
            break
        log.warning("MediaMTX exited (code=%s) — restarting in %.0fs", code, backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, 10.0)
        # @claude After a child restart the runtime source config is gone;
        # @claude re-apply the saved profile through the normal startup path.
        threading.Thread(target=camera.startup_apply, daemon=True).start()


def _stop_mediamtx() -> None:
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


@app.get("/health")
def health():
    with _mtx_lock:
        alive = _mtx_proc is not None and _mtx_proc.poll() is None
    return {"status": "ok", "mediamtx_alive": alive}


@app.get("/profile")
def get_profile():
    """Return the profile with the password reduced to password_set (FR-013)."""
    return camera.profile_view()


@app.post("/profile")
async def register_profile(request: Request):
    """Persist a profile into the registered slot (FR-009, FR-010). Does not
    connect the source (FR-048) and does not start analysis (FR-025)."""
    body = await request.json()
    return camera.register(body)


@app.post("/streaming/start")
def streaming_start():
    """Promote the registered profile and connect the source (SRS §2.3 (3),
    FR-048). Idempotent; doubles as a restart."""
    return camera.streaming_start()


@app.post("/streaming/stop")
def streaming_stop():
    """Detach the source (SRS §2.3 (3), FR-049). The router cascades the
    analysis and buffer stops separately."""
    return camera.streaming_stop()


@app.post("/ptz")
async def control_ptz(request: Request):
    body = await request.json()
    action = body.get("action")
    ok = True

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
        if presets is not None:
            camera.save_presets(presets)
        ok = presets is not None
    elif action == "goto":
        try:
            slot = int(body.get("slot"))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid preset slot")
        preset = ptz.get_preset(slot)
        if preset is not None:
            threading.Thread(
                target=ptz.absolute_move,
                args=(preset["pan"], preset["tilt"]),
                daemon=True,
            ).start()
        else:
            ok = False
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

    return {"ok": ok}


@app.get("/status")
def status():
    """PTZ position snapshot for the router's monitoring merge (SDD §6.4 (4))."""
    current = ptz.get_current()
    with _mtx_lock:
        alive = _mtx_proc is not None and _mtx_proc.poll() is None
    return {
        "ptz_pan": current["pan"],
        "ptz_tilt": current["tilt"],
        # @claude JSON keys are strings; ptz_presets keeps the slot-number list
        # @claude for existing consumers, ptz_preset_positions adds the stored
        # @claude coordinates per slot (slot -> {pan, tilt}).
        "ptz_presets": sorted(ptz.get_presets()),
        "ptz_preset_positions": ptz.get_presets(),
        "ptz_patrol": ptz.get_patrol(),
        **camera.status_view(),
        "mediamtx_alive": alive,
    }

"""
Babycat controller — video source profile, streamer source config, PTZ.

Internal only: no port is published; the router is the sole caller
(SDD §4.3, §6.3). No authentication — requests that reach here already
passed the router.

@claude
"""

import logging
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

import camera
import ptz

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    config = camera.load()
    ptz.load_home(config.get("ptz_home") if config else None)

    threading.Thread(target=camera.startup_apply, daemon=True).start()
    threading.Thread(target=ptz.poll_loop, daemon=True).start()
    threading.Thread(target=camera.source_watchdog, daemon=True).start()
    yield


app = FastAPI(title="Babycat controller", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/profile")
def get_profile():
    """Return the profile with the password reduced to password_set (FR-013)."""
    return camera.profile_view()


@app.post("/profile")
async def apply_profile(request: Request):
    """Persist and activate a profile. Does not start analysis (FR-025)."""
    body = await request.json()
    return camera.apply(body)


@app.post("/activate")
def activate():
    """Instruct the streamer to redistribute the saved source (SRS §2.3 (4))."""
    return camera.activate_saved()


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
        home = ptz.save_home()
        if home:
            camera.save({"ptz_home": home})
        ok = home is not None
    elif action == "goto":
        saved = ptz.get_saved()
        if saved["pan"] is not None:
            threading.Thread(
                target=ptz.absolute_move,
                args=(saved["pan"], saved["tilt"]),
                daemon=True,
            ).start()
        else:
            ok = False

    return {"ok": ok}


@app.get("/status")
def status():
    """PTZ position snapshot for the router's monitoring merge (SDD §6.4 (4))."""
    current = ptz.get_current()
    saved = ptz.get_saved()
    return {
        "ptz_pan": current["pan"],
        "ptz_tilt": current["tilt"],
        "ptz_saved_pan": saved["pan"],
        "ptz_saved_tilt": saved["tilt"],
        "profile_configured": camera.load() is not None,
    }

"""fakecam server entry point.

Bridges three event loops:
  - GLib MainLoop (GStreamer / gst-rtsp-server) in a daemon thread.
  - asyncio loop (FastAPI / uvicorn) in the main thread.
  - SettingsStore observer callbacks, invoked from whichever thread
    happens to perform the update; the RtspServer's own lock keeps
    these safe.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

import uvicorn
from gi.repository import GLib

from .api import build_app
from .rtsp_server import RtspServer
from .settings import SettingsStore


log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    videos_dir = os.environ.get("VIDEOS_DIR", "/videos")
    state_path = os.environ.get("STATE_PATH", "/state.json")
    api_port = int(os.environ.get("API_PORT", "8090"))

    log.info("=== fakecam server start ===")
    log.info("  VIDEOS_DIR : %s", videos_dir)
    log.info("  STATE_PATH : %s", state_path)
    log.info("  API_PORT   : %d", api_port)

    settings_store = SettingsStore(state_path)
    rtsp_server = RtspServer()
    initial = settings_store.get()
    rtsp_server.start(initial)
    prev_settings = initial

    def on_settings_change(new):
        # @claude Restart RTSP server when transport-level fields change;
        # @claude encoding fields are picked up by apply_settings without a restart.
        nonlocal prev_settings
        rtsp_server.apply_settings(new)
        transport_changed = (
            prev_settings.port != new.port
            or prev_settings.rtsp_path != new.rtsp_path
            or prev_settings.auth_user != new.auth_user
            or prev_settings.auth_password != new.auth_password
        )
        prev_settings = new
        if transport_changed:
            log.info("settings: transport-level change — restarting RTSP server")
            try:
                rtsp_server.restart(new)
            except Exception:
                log.exception("RTSP server restart failed")

    settings_store.subscribe(on_settings_change)

    glib_loop = GLib.MainLoop()
    glib_thread = threading.Thread(
        target=glib_loop.run, daemon=True, name="glib-mainloop"
    )
    glib_thread.start()

    app = build_app(
        videos_dir=videos_dir,
        settings_store=settings_store,
        rtsp_server=rtsp_server,
    )

    try:
        uvicorn.run(app, host="0.0.0.0", port=api_port, log_level="info")
    finally:
        try:
            rtsp_server.stop()
        finally:
            glib_loop.quit()


if __name__ == "__main__":
    main()

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
from .events import EventBus
from .playback import PlaybackController
from .playlist import PlaylistStore
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
    state_path = os.environ.get("STATE_PATH", "/state/state.json")
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

    playlist = PlaylistStore()
    playback = PlaybackController(playlist, rtsp_server, videos_dir)
    event_bus = EventBus()
    rtsp_server.set_post_configure_callback(playback.on_post_configure)
    rtsp_server.set_advance_callback(playback.on_advance)
    rtsp_server.set_exhausted_callback(playback.on_exhausted)

    def on_settings_change(new):
        nonlocal prev_settings
        rtsp_server.apply_settings(new)
        transport_changed = any(
            getattr(prev_settings, f) != getattr(new, f) for f in (
                "port", "rtsp_path", "auth_user", "auth_password",
            )
        )
        prev_settings = new
        event_bus.publish({"type": "settings", "settings": new.model_dump()})
        if transport_changed:
            log.info("settings: transport-level change — restarting RTSP server")
            try:
                rtsp_server.restart(new)
            except Exception:
                log.exception("RTSP server restart failed")

    settings_store.subscribe(on_settings_change)

    def on_playback_state(state, mode):
        event_bus.publish({"type": "playlist", "playlist": state.model_dump()})
        event_bus.publish({"type": "mode", "mode": mode.model_dump()})

    playback.subscribe(on_playback_state)

    def on_playlist_change(_items):
        # @claude PlaylistStore mutations (add/remove) only flow through
        # @claude PlaybackController._broadcast while playing; when stopped the
        # @claude controller's listener returns early. Subscribe to the store
        # @claude directly so SSE clients see add/remove immediately even when
        # @claude playback is idle.
        event_bus.publish({"type": "playlist", "playlist": playback.state().model_dump()})

    playlist.subscribe(on_playlist_change)

    glib_loop = GLib.MainLoop()
    glib_thread = threading.Thread(
        target=glib_loop.run, daemon=True, name="glib-mainloop"
    )
    glib_thread.start()

    app = build_app(
        videos_dir=videos_dir,
        settings_store=settings_store,
        rtsp_server=rtsp_server,
        playlist=playlist,
        playback=playback,
        event_bus=event_bus,
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

"""gst-rtsp-server wrapper.

Owns one `GstRtspServer.RTSPServer` instance with a single dynamic
factory mounted at the configured RTSP path. Phase 1 supports
streaming one mp4 at a time via `set_current(path)`; Phase 2 will
replace the launch builder with a concat-based variant.

Authentication uses RTSP Basic auth seeded from `Settings`. The server
must be restarted (call `stop()` then `start()`) for port or rtsp_path
changes to take effect.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GLib, Gst, GstRtspServer  # noqa: E402

from . import pipeline
from .schemas import Settings


log = logging.getLogger(__name__)


_ROLE = "fakecam-user"


class _DynamicFactory(GstRtspServer.RTSPMediaFactory):
    """Factory whose launch string follows a provider callback."""

    def __init__(self, launch_provider: Callable[[], Optional[str]]):
        super().__init__()
        self._launch_provider = launch_provider
        self.set_shared(True)

    def do_create_element(self, _url):
        launch = self._launch_provider()
        if not launch:
            log.warning("RTSP factory has no current launch; refusing client")
            return None
        try:
            return Gst.parse_launch(launch)
        except GLib.Error as e:
            log.error("RTSP launch parse failed: %s", e)
            return None


class RtspServer:
    def __init__(self):
        Gst.init(None)
        self._lock = threading.Lock()
        self._server: Optional[GstRtspServer.RTSPServer] = None
        self._factory: Optional[_DynamicFactory] = None
        self._attach_id: Optional[int] = None
        self._settings: Optional[Settings] = None
        self._current_path: Optional[Path] = None
        self._eos_callback: Optional[Callable[[], None]] = None

    def set_eos_callback(self, cb: Callable[[], None]) -> None:
        """Register a hook invoked from the GLib thread on pipeline EOS."""
        self._eos_callback = cb

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self, settings: Settings) -> None:
        with self._lock:
            if self._server is not None:
                raise RuntimeError("RTSP server already running")
            self._settings = settings
            server = GstRtspServer.RTSPServer()
            server.set_service(str(settings.port))

            factory = _DynamicFactory(self._current_launch)
            # @claude `add_role` is a variadic C function and is not exposed by the
            # @claude Python GI bindings; use the structure-based alternative.
            perm_struct = Gst.Structure.new_from_string(
                f"{_ROLE},"
                "media.factory.access=(boolean)true,"
                "media.factory.construct=(boolean)true"
            )
            if perm_struct is None:
                raise RuntimeError("failed to build factory permissions structure")
            factory.add_role_from_structure(perm_struct)

            auth = GstRtspServer.RTSPAuth()
            # @claude Python GI exposes only `RTSPToken.new()` with no args; set
            # @claude role fields explicitly afterwards.
            token = GstRtspServer.RTSPToken.new()
            token.set_string("media.factory.role", _ROLE)
            basic = GstRtspServer.RTSPAuth.make_basic(
                settings.auth_user, settings.auth_password
            )
            auth.add_basic(basic, token)
            server.set_auth(auth)

            mounts = server.get_mount_points()
            mounts.add_factory(settings.rtsp_path, factory)

            factory.connect("media-configure", self._on_media_configure)

            self._attach_id = server.attach(None)
            self._server = server
            self._factory = factory
            log.info(
                "RTSP server listening: rtsp://%s:%s@<host>:%d%s",
                settings.auth_user, settings.auth_password,
                settings.port, settings.rtsp_path,
            )

    def stop(self) -> None:
        with self._lock:
            if self._attach_id is not None:
                GLib.Source.remove(self._attach_id)
                self._attach_id = None
            self._server = None
            self._factory = None
            log.info("RTSP server stopped")

    def restart(self, settings: Settings) -> None:
        self.stop()
        self.start(settings)

    # ── current source ───────────────────────────────────────────────────────

    def set_current(self, abs_path: Path) -> None:
        with self._lock:
            self._current_path = abs_path
            log.info("RTSP current source: %s", abs_path)

    def clear_current(self) -> None:
        with self._lock:
            self._current_path = None

    def apply_settings(self, settings: Settings) -> None:
        """Update encoding-affecting fields without restarting the server.

        Port and auth changes require restart() and are not applied here.
        """
        with self._lock:
            if self._settings is None:
                self._settings = settings
                return
            self._settings = self._settings.model_copy(update={
                "resolution": settings.resolution,
                "fps": settings.fps,
                "bitrate_mbps": settings.bitrate_mbps,
                "audio": settings.audio,
            })

    # ── internals ────────────────────────────────────────────────────────────

    def _current_launch(self) -> Optional[str]:
        with self._lock:
            if self._current_path is None or self._settings is None:
                return None
            return pipeline.build_launch(str(self._current_path), self._settings)

    def _on_media_configure(self, _factory, media) -> None:
        pipeline_elem = media.get_element()
        bus = pipeline_elem.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_bus_eos)

    def _on_bus_eos(self, _bus, _msg) -> None:
        cb = self._eos_callback
        if cb is not None:
            try:
                cb()
            except Exception:
                log.exception("EOS callback failed")

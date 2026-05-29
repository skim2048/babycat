"""gst-rtsp-server wrapper with concat-based seamless playlist transitions.

Lifecycle:
  - The `_DynamicFactory` produces a pipeline from `pipeline.build_initial_launch`,
    which always includes a `concat` element named "concat" with the initial
    file already linked to `concat.sink_0`.
  - On `media-configure` the wrapper grabs references to the media's
    pipeline and concat elements and stores them in `_session`. From that
    point on, the playback controller calls `enqueue_next` to feed the
    next item into concat ahead of the natural EOS transition.
  - When the media is unprepared (no more clients) the session is dropped.
    The launch string for the *next* fresh media uses whatever `_initial`
    was last set to.

Threading:
  - All wrapper methods take `_lock` so the API thread and the GLib
    callback thread cannot race on `_session` state.
  - Any GStreamer manipulation that must happen on the GLib thread is
    dispatched via `GLib.idle_add`; everything else can happen inline
    because the relevant elements are thread-safe.
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


def _build_input_chain(file_path: str) -> Optional[Gst.Bin]:
    """Build an input chain as a Gst.Bin with a single ghost `src` pad.

    Construction is explicit rather than via `Gst.parse_bin_from_description`
    because the latter's delayed-link mechanism for qtdemux's dynamic
    pads is invalidated once the bin is reparented into another pipeline,
    causing the video pad to never link. We replicate the same logical
    pipeline (`filesrc ! qtdemux -[video]-> h264parse ! avdec_h264`)
    with an explicit `pad-added` callback so the link is set up at
    runtime against this chain's own elements.
    """
    chain = Gst.Bin.new(None)
    filesrc = Gst.ElementFactory.make("filesrc", None)
    qtdemux = Gst.ElementFactory.make("qtdemux", None)
    h264parse = Gst.ElementFactory.make("h264parse", None)
    avdec = Gst.ElementFactory.make("avdec_h264", None)
    if not all((filesrc, qtdemux, h264parse, avdec)):
        return None
    filesrc.set_property("location", file_path)
    for elem in (filesrc, qtdemux, h264parse, avdec):
        chain.add(elem)
    if not filesrc.link(qtdemux):
        return None
    if not h264parse.link(avdec):
        return None

    h264_sink = h264parse.get_static_pad("sink")

    def on_pad_added(_demux, pad: Gst.Pad) -> None:
        if h264_sink.is_linked():
            return
        caps = pad.query_caps(None)
        struct = caps.get_structure(0) if caps and caps.get_size() > 0 else None
        if struct is None or not struct.get_name().startswith("video/"):
            return
        pad.link(h264_sink)

    qtdemux.connect("pad-added", on_pad_added)

    src_pad = avdec.get_static_pad("src")
    ghost = Gst.GhostPad.new("src", src_pad)
    ghost.set_active(True)
    chain.add_pad(ghost)
    return chain


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


class _Session:
    """Per-media state shared between the API thread and the GLib bus."""

    __slots__ = (
        "media",
        "pipeline",
        "concat",
        "queued_bin",
        "queued_sink_pad",
        "previous_active_pad_name",
    )

    def __init__(self, media, pipeline_elem, concat):
        self.media = media
        self.pipeline = pipeline_elem
        self.concat = concat
        self.queued_bin: Optional[Gst.Element] = None
        self.queued_sink_pad: Optional[Gst.Pad] = None
        self.previous_active_pad_name: Optional[str] = None


class RtspServer:
    def __init__(self):
        Gst.init(None)
        self._lock = threading.Lock()
        self._server: Optional[GstRtspServer.RTSPServer] = None
        self._factory: Optional[_DynamicFactory] = None
        self._attach_id: Optional[int] = None
        self._settings: Optional[Settings] = None
        self._initial: Optional[Path] = None
        self._session: Optional[_Session] = None
        self._post_configure_cb: Optional[Callable[[], None]] = None
        self._advance_cb: Optional[Callable[[], None]] = None
        self._exhausted_cb: Optional[Callable[[], None]] = None

    # ── callback registration ────────────────────────────────────────────────

    def set_post_configure_callback(self, cb: Callable[[], None]) -> None:
        """Invoked from the GLib thread once per media construction."""
        self._post_configure_cb = cb

    def set_advance_callback(self, cb: Callable[[], None]) -> None:
        """Invoked from the GLib thread when concat moves to a new active pad."""
        self._advance_cb = cb

    def set_exhausted_callback(self, cb: Callable[[], None]) -> None:
        """Invoked when the entire concat (i.e. the playlist) reaches EOS."""
        self._exhausted_cb = cb

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self, settings: Settings) -> None:
        with self._lock:
            if self._server is not None:
                raise RuntimeError("RTSP server already running")
            self._settings = settings
            server = GstRtspServer.RTSPServer()
            server.set_service(str(settings.port))

            factory = _DynamicFactory(self._current_launch)
            # @claude Disable gst-rtsp-server's auto suspend; the suspend phase has a
            # @claude documented FIXME for "dynamic pipelines" and corrupts the media
            # @claude when we add concat inputs after prepare.
            factory.set_suspend_mode(GstRtspServer.RTSPSuspendMode.NONE)
            perm_struct = Gst.Structure.new_from_string(
                f"{_ROLE},"
                "media.factory.access=(boolean)true,"
                "media.factory.construct=(boolean)true"
            )
            if perm_struct is None:
                raise RuntimeError("failed to build factory permissions structure")
            factory.add_role_from_structure(perm_struct)

            auth = GstRtspServer.RTSPAuth()
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
            self._session = None
            log.info("RTSP server stopped")

    def restart(self, settings: Settings) -> None:
        self.stop()
        self.start(settings)

    # ── playlist driving ─────────────────────────────────────────────────────

    def set_initial(self, abs_path: Optional[Path]) -> None:
        """Set the file used by the next media construction.

        Has no effect on an already-active session — the in-flight pipeline
        keeps streaming whatever it was started with.
        """
        with self._lock:
            self._initial = abs_path
            log.info("RTSP initial source: %s", abs_path)

    def enqueue_next(self, abs_path: Optional[Path]) -> None:
        """Queue a file as the next concat input, replacing any prior queue.

        On the GLib thread to avoid racing with the streaming pipeline. If
        no media is active this is a no-op (the file will play via
        `set_initial` when a client next connects).
        """
        GLib.idle_add(self._do_enqueue_next, abs_path)

    def stop_streaming(self) -> None:
        """Drop the queue and EOS the active input. Used to satisfy stop()."""
        GLib.idle_add(self._do_stop_streaming)

    def apply_settings(self, settings: Settings) -> None:
        """Capture new encoding/transport fields. Applied on next media creation."""
        with self._lock:
            self._settings = settings

    def refresh_media(self) -> None:
        """Unprepare the active media so the next client connection rebuilds
        the pipeline with the current settings. No-op if there is no active
        session. Used when encoding settings change but the RTSP server
        itself does not need a transport restart."""
        GLib.idle_add(self._do_refresh_media)

    def has_active_session(self) -> bool:
        with self._lock:
            return self._session is not None

    # ── GStreamer-thread workers ─────────────────────────────────────────────

    def _do_enqueue_next(self, abs_path: Optional[Path]) -> bool:
        with self._lock:
            session = self._session
        if session is None:
            return False
        self._release_queued(session)
        if abs_path is None:
            return False
        chain = _build_input_chain(str(abs_path))
        if chain is None:
            log.error("enqueue_next: failed to build input chain")
            return False
        sink_pad = session.concat.request_pad_simple("sink_%u")
        if sink_pad is None:
            log.error("enqueue_next: concat refused new sink pad")
            return False
        session.pipeline.add(chain)
        if chain.get_parent() is not session.pipeline:
            log.error("enqueue_next: chain failed to reparent into pipeline bin")
            session.concat.release_request_pad(sink_pad)
            return False
        src_pad = chain.get_static_pad("src")
        link_ret = src_pad.link(sink_pad)
        if link_ret != Gst.PadLinkReturn.OK:
            log.error("enqueue_next: pad link failed (%s)", link_ret)
            session.pipeline.remove(chain)
            session.concat.release_request_pad(sink_pad)
            return False
        # @claude Drive the chain to PLAYING explicitly. sync_state_with_parent
        # @claude returns a bool that hides whether a transition was queued; if
        # @claude sync returns "no change" the subsequent get_state has nothing
        # @claude to wait for and the chain stays in READY, which leaves the
        # @claude dynamic qtdemux pad disconnected. set_state surfaces ASYNC vs
        # @claude SUCCESS so we can actually block on completion.
        change = chain.set_state(Gst.State.PLAYING)
        if change == Gst.StateChangeReturn.FAILURE:
            log.error("enqueue_next: set_state(PLAYING) failed; cleaning up")
            session.pipeline.remove(chain)
            session.concat.release_request_pad(sink_pad)
            return False
        ret, current, pending = chain.get_state(5 * Gst.SECOND)
        if current != Gst.State.PLAYING:
            log.warning(
                "enqueue_next: chain only reached %s (pending=%s, ret=%s) after 5s",
                current.value_nick, pending.value_nick, ret.value_nick,
            )
        session.queued_bin = chain
        session.queued_sink_pad = sink_pad
        log.info(
            "enqueued next: %s (pad=%s, state=%s, change=%s)",
            abs_path, sink_pad.get_name(), current.value_nick, change.value_nick,
        )
        return False  # @claude single-shot idle_add

    def _do_refresh_media(self) -> bool:
        with self._lock:
            session = self._session
        if session is None:
            return False
        log.info("refresh_media: unpreparing active media to apply new settings")
        try:
            session.media.unprepare()
        except Exception:
            log.exception("refresh_media: unprepare failed")
        return False

    def _do_stop_streaming(self) -> bool:
        with self._lock:
            session = self._session
        if session is None:
            return False
        self._release_queued(session)
        active = session.concat.get_property("active-pad")
        if active is not None:
            peer = active.get_peer()
            if peer is not None:
                peer.send_event(Gst.Event.new_eos())
        return False

    def _release_queued(self, session: _Session) -> None:
        if session.queued_bin is None:
            return
        chain = session.queued_bin
        sink_pad = session.queued_sink_pad
        session.queued_bin = None
        session.queued_sink_pad = None
        try:
            chain.set_state(Gst.State.NULL)
            session.pipeline.remove(chain)
        except Exception:
            log.exception("release_queued: pipeline cleanup failed")
        if sink_pad is not None:
            try:
                session.concat.release_request_pad(sink_pad)
            except Exception:
                log.exception("release_queued: pad release failed")

    # ── media construction hooks ─────────────────────────────────────────────

    def _current_launch(self) -> Optional[str]:
        with self._lock:
            if self._initial is None or self._settings is None:
                return None
            return pipeline.build_initial_launch(str(self._initial), self._settings)

    def _on_media_configure(self, _factory, media) -> None:
        pipeline_elem = media.get_element()
        concat = pipeline_elem.get_by_name("concat") if pipeline_elem else None
        if concat is None:
            log.error("media-configure: concat element not found")
            return
        session = _Session(media, pipeline_elem, concat)
        active = concat.get_property("active-pad")
        if active is not None:
            session.previous_active_pad_name = active.get_name()
        concat.connect("notify::active-pad", self._on_active_pad_change)
        bus = pipeline_elem.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_bus_eos)
        bus.connect("message::error", self._on_bus_error)
        bus.connect("message::warning", self._on_bus_warning)
        media.connect("unprepared", self._on_unprepared)
        media.connect("prepared", self._on_prepared)
        with self._lock:
            self._session = session
        log.info("media configured; initial active=%s", session.previous_active_pad_name)

    def _on_prepared(self, _media) -> None:
        log.info("media prepared — running post_configure hook")
        if self._post_configure_cb is not None:
            try:
                self._post_configure_cb()
            except Exception:
                log.exception("post_configure callback failed")

    def _on_bus_error(self, _bus, msg) -> None:
        err, debug = msg.parse_error()
        log.error("pipeline error: %s | debug=%s", err, debug)

    def _on_bus_warning(self, _bus, msg) -> None:
        warn, debug = msg.parse_warning()
        log.warning("pipeline warning: %s | debug=%s", warn, debug)

    def _on_active_pad_change(self, concat, _pspec) -> None:
        active = concat.get_property("active-pad")
        if active is None:
            return
        new_name = active.get_name()
        with self._lock:
            session = self._session
            if session is None:
                return
            prev_name = session.previous_active_pad_name
            session.previous_active_pad_name = new_name
            # @claude The freshly-active pad was the queued one. Clear the queue
            # @claude reference so the next enqueue_next call doesn't try to
            # @claude tear down a chain that is now the live source.
            if session.queued_sink_pad is not None and session.queued_sink_pad.get_name() == new_name:
                session.queued_bin = None
                session.queued_sink_pad = None
        log.info("concat advanced: %s → %s", prev_name, new_name)
        if self._advance_cb is not None:
            try:
                self._advance_cb()
            except Exception:
                log.exception("advance callback failed")

    def _on_bus_eos(self, _bus, _msg) -> None:
        log.info("pipeline EOS")
        if self._exhausted_cb is not None:
            try:
                self._exhausted_cb()
            except Exception:
                log.exception("exhausted callback failed")

    def _on_unprepared(self, _media) -> None:
        log.info("media unprepared")
        with self._lock:
            self._session = None

"""
NVENC segment recorder (SDD §2.4 (3), §4.4).

Re-encodes the redistributed stream with the hardware encoder, forcing a
keyframe every segment so clips can be cut on 1-second boundaries without
burning CPU. Segments land in tmpfs and are purged past the retention
window. The pipeline starts only while the buffer is active (§2.4 (4))
and reconnects on its own with exponential backoff (FR-046).

@claude
"""

import logging
import os
import threading
import time

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from rollover import (
    ensure_segment_dir,
    latest_segment_age_seconds,
    list_segments,
    purge_old_segments,
    segment_path_for_time,
)
from status import status

log = logging.getLogger(__name__)

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://streamer:8554/live")
SEGMENT_DIR = os.getenv("TRIGGER_SEGMENT_DIR", "/run/babycat-segments/live")
SEGMENT_TIME = int(os.getenv("TRIGGER_SEGMENT_TIME", "1"))
SEGMENT_RETENTION = int(os.getenv("TRIGGER_SEGMENT_RETENTION", "15"))
ENCODE_BITRATE = int(os.getenv("RECORDER_ENCODE_BITRATE", "4000000"))
# @claude iframeinterval is in frames; assumes the source frame rate. A slower
# @claude camera only lengthens segments — selection tolerates that.
ENCODE_FPS = int(os.getenv("RECORDER_ENCODE_FPS", "30"))

_BACKOFF_MAX = 10.0


def build_pipeline_str() -> str:
    gop = max(1, ENCODE_FPS * SEGMENT_TIME)
    return (
        f"rtspsrc location={MEDIAMTX_URL} latency=0 protocols=tcp "
        "! rtph264depay ! h264parse ! nvv4l2decoder "
        "! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 "
        f"! nvv4l2h264enc bitrate={ENCODE_BITRATE} iframeinterval={gop} idrinterval={gop} "
        "insert-sps-pps=true maxperf-enable=true "
        "! h264parse ! splitmuxsink name=smux muxer=mpegtsmux "
        f"max-size-time={SEGMENT_TIME * 1_000_000_000}"
    )


class SegmentRecorder:
    """Owns the encoder pipeline thread. start()/stop() are idempotent."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and not self._stop.is_set():
                return
            # @claude New generation: a start landing while the previous worker
            # @claude is still winding down must not be swallowed. The old
            # @claude worker keeps its own stop event; the new one joins it
            # @claude before touching the pipeline, so two encoders never run
            # @claude at once.
            previous = self._thread
            stop = threading.Event()
            self._stop = stop
            self._thread = threading.Thread(
                target=self._worker, args=(stop, previous), daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop.set()

    # ── worker ───────────────────────────────────────────────────────────────

    def _worker(self, stop: threading.Event, previous: threading.Thread | None) -> None:
        if previous is not None:
            previous.join()
        Gst.init(None)
        segment_dir = ensure_segment_dir(SEGMENT_DIR)
        backoff = 1.0
        log.info("segment recorder started (dir=%s, segment=%ds)", segment_dir, SEGMENT_TIME)

        while not stop.is_set():
            purge_old_segments(segment_dir, retain_since=time.time() - SEGMENT_RETENTION)
            pipeline = None
            try:
                pipeline = Gst.parse_launch(build_pipeline_str())
                smux = pipeline.get_by_name("smux")
                smux.connect("format-location", self._on_format_location)
                pipeline.set_state(Gst.State.PLAYING)
                status.set_segment_recorder("running", segment_count=len(list_segments(segment_dir)))
                backoff = self._watch(pipeline, segment_dir, backoff, stop)
            except Exception as e:
                log.error("segment recorder pipeline error: %s", e)
                status.set_segment_recorder("error", error=str(e)[:240])
            finally:
                if pipeline is not None:
                    pipeline.set_state(Gst.State.NULL)
            if stop.is_set():
                break
            # @claude Interruptible: a stop during backoff must end this
            # @claude generation promptly so a following start is not delayed.
            stop.wait(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)

        status.set_segment_recorder("disabled", last_segment_age_s=None)
        log.info("segment recorder stopped")

    def _watch(self, pipeline, segment_dir, backoff: float, stop: threading.Event) -> float:
        """Poll the bus until stop/error. Returns the next backoff to use."""
        bus = pipeline.get_bus()
        healthy_since: float | None = None
        while not stop.is_set():
            msg = bus.timed_pop_filtered(
                1_000_000_000, Gst.MessageType.ERROR | Gst.MessageType.EOS
            )
            age = latest_segment_age_seconds(segment_dir)
            status.set_segment_recorder(
                "running",
                segment_count=len(list_segments(segment_dir)),
                last_segment_age_s=age,
            )
            purge_old_segments(segment_dir, retain_since=time.time() - SEGMENT_RETENTION)
            if msg is not None:
                detail = ""
                if msg.type == Gst.MessageType.ERROR:
                    err, dbg = msg.parse_error()
                    detail = str(err)
                log.warning("segment recorder pipeline ended (%s) %s", msg.type, detail)
                status.set_segment_recorder("error", error=detail[:240])
                return backoff
            # @claude Fresh segments flowing for a while — reset the backoff.
            if age is not None and age < SEGMENT_TIME * 3:
                if healthy_since is None:
                    healthy_since = time.time()
                elif time.time() - healthy_since > 10:
                    backoff = 1.0
            else:
                healthy_since = None
        return backoff

    @staticmethod
    def _on_format_location(_smux, _fragment_id) -> str:
        """Name each fragment by its wall-clock open time so selection can map
        segments back to the event window (rollover.parse_segment_start)."""
        return str(segment_path_for_time(SEGMENT_DIR, time.time()))


recorder = SegmentRecorder()

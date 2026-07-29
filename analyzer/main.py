"""
Babycat analyzer — entry point.

Pipeline:
  rtspsrc (streamer) -> rtph264depay -> h264parse -> nvv4l2decoder
  -> nvvidconv (RGBA) -> videorate -> appsink
  -> RingBuffer -> VLM inference -> keyword match -> event notify (recorder)

Clip recording, event history, and hardware monitoring live in the
recorder (SDD §4.4); this process only judges events and notifies.

@claude
"""

import logging
import os
import queue
import sys
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import numpy as np
from PIL import Image

import settings
from notify import notify_event
from vlm_worker import VlmProcess
from state import state as app_state
from server import set_start_analysis_callback, set_stop_analysis_callback, start_server
from pipeline_lifecycle import PipelineLifecycle

log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://streamer:8554/live")

# @claude VLM_MODELS / holder singletons live in a dedicated module to avoid the
# @claude double-import trap caused by main.py being loaded both as __main__ and as `main`.
from holder import VLM_MODELS, set_holder as _set_holder, set_available as _set_available
MODEL_ID = VLM_MODELS[0]

TARGET_FPS = float(os.getenv("TARGET_FPS", "1.0"))
N_FRAMES   = int(os.getenv("N_FRAMES",   "4"))

RING_SIZE = int(os.getenv("RING_SIZE", "30"))

SERVER_PORT = int(os.getenv("SERVER_PORT", "8300"))

# @claude SigLIP input resolution; the VLM resizes to 384x384 internally.
VLM_INPUT_SIZE = (384, 384)


# ── Ring buffer ──────────────────────────────────────────────────────────────

class RingBuffer:
    """
    Fixed-size circular buffer for VLM context frames. Pushed from the
    GStreamer callback thread and read via latest() from the inference
    thread.

    @claude
    """

    def __init__(self, maxlen: int):
        self._buf: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: Image.Image, captured_at: float) -> None:
        with self._lock:
            self._buf.append((captured_at, frame))

    def latest_samples(self, n: int) -> list:
        """Return the most recent n `(captured_at, frame)` samples."""
        with self._lock:
            samples = list(self._buf)
        return samples[-n:] if len(samples) >= n else samples

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


# ── VLM model holder (switch support) ────────────────────────────────────────

class ModelHolder:
    """
    Carries the current VLM model name plus any pending switch request
    across threads. The model object itself lives in a child process
    (see vlm_worker.VlmProcess); this holder only mediates the switch
    request between the HTTP handler thread and the inference worker.

    The worker checks pop_request() at the top of each iteration, so a
    switch only happens between inferences, never mid-generation.

    @claude
    """
    def __init__(self, name: str):
        self._lock = threading.Lock()
        self.name = name
        self._switch_to: str | None = None

    def request_switch(self, name: str) -> bool:
        if name not in VLM_MODELS:
            return False
        with self._lock:
            if name == self.name and self._switch_to is None:
                return True  # @claude already the active model — treat as no-op success.
            self._switch_to = name
        return True

    def pop_request(self) -> str | None:
        with self._lock:
            target, self._switch_to = self._switch_to, None
            return target


def _so_path(model_id: str) -> Path:
    """MLC compile artifact path; depends on NanoLLM's internal layout. @claude"""
    base = model_id.split("/")[-1]
    return Path(f"/data/models/mlc/dist/{base}/ctx4096/{base}-q4f16_ft/{base}-q4f16_ft-cuda.so")


def _hf_snapshot_exists(model_id: str) -> bool:
    """Whether the HF snapshot cache exists; when absent _precompile_one downloads first. @claude"""
    return Path(f"/data/models/huggingface/models--{model_id.replace('/', '--')}").exists()


def _precompile_one(model_id: str) -> bool:
    """
    Invoke NanoLLM.from_pretrained in a subprocess so the .so cache is
    produced and the process exits. The OS reclaims CUDA/TVM memory on
    subprocess exit, which prevents OOM from leftover state when models
    are compiled sequentially.

    @claude
    """
    import subprocess
    log.info("Precompiling VLM (subprocess): %s", model_id)
    t0 = time.time()
    code = (
        "from nano_llm import NanoLLM; "
        f"NanoLLM.from_pretrained({model_id!r}, api='mlc', quantization='q4f16_ft')"
    )
    result = subprocess.run([sys.executable, "-c", code], check=False)
    if result.returncode != 0:
        log.error("Precompile failed for %s (exit %d)", model_id, result.returncode)
        return False
    log.info("Precompiled %s in %.1fs", model_id, time.time() - t0)
    return True


def _precompile_all(models: list[str]) -> list[str]:
    """
    Compile only models that lack a cached .so. Returns the list of models
    whose cache is complete. If the default model (first entry) fails to
    compile, raise RuntimeError — booting is pointless without it.
    Secondary model failures are dropped silently.

    @claude
    """
    available = []
    for m in models:
        if _so_path(m).exists():
            log.info("MLC cache hit: %s", m)
            available.append(m)
            continue
        app_state.set_vlm_current_model(m)  # @claude Surface the model currently being compiled in the UI.
        if not _hf_snapshot_exists(m):
            app_state.set_vlm_state("downloading")
        else:
            app_state.set_vlm_state("compiling")
        ok = _precompile_one(m)
        if ok:
            available.append(m)
        elif m == models[0]:
            raise RuntimeError(f"default model precompile failed: {m}")
        else:
            log.warning("Dropping %s from available models (precompile failed)", m)
    return available


def _perform_switch(holder: ModelHolder, vlm_proc: VlmProcess, target: str) -> None:
    """
    Switch the live VLM child to `target`. vlm_proc.switch() kills the
    current child first, so the previous model's CUDA/TVM/TensorRT memory
    is reclaimed by the OS before the new model loads. Rolls back to the
    previous model on failure.

    Assumes any in-flight inference has already finished.

    @claude
    """
    prev = holder.name
    log.info("Switching VLM: %s → %s", prev, target)
    app_state.set_vlm_state("switching")
    app_state.set_vlm_current_model(target)  # @claude Pre-apply the target to the UI so the selector reflects intent.

    try:
        vlm_proc.switch(target)
    except Exception as e:
        log.error("VLM switch failed (%s → %s): %s", prev, target, e)
        app_state.set_vlm_state("error", f"{target}: {str(e)[:200]}")
        try:
            vlm_proc.switch(prev)
            app_state.set_vlm_current_model(prev)
            app_state.set_vlm_state("ready")
            log.info("Rolled back to %s", prev)
        except Exception as e2:
            log.error("Rollback to %s also failed: %s", prev, e2)
        return

    holder.name = target
    app_state.set_vlm_state("ready")
    log.info("VLM switch complete: %s", target)


# ── Inference worker thread ──────────────────────────────────────────────────

def inference_worker(holder: "ModelHolder", vlm_proc: VlmProcess, ring: RingBuffer,
                     infer_queue: queue.Queue) -> None:
    """
    When the appsink callback signals infer_queue, pull the latest
    N_FRAMES from `ring`, run VLM inference in the child process, match
    keywords, and notify the recorder on an event.

    Each iteration starts by consulting holder.pop_request() so model
    switches are only performed between inferences, never mid-generation.

    @claude
    """
    log.info("VLM inference thread started")
    while True:
        # @claude Handle pending switch requests at the boundary between inferences.
        target = holder.pop_request()
        if target and target != holder.name:
            _perform_switch(holder, vlm_proc, target)

        try:
            infer_queue.get(timeout=5)
        except queue.Empty:
            continue

        samples = ring.latest_samples(N_FRAMES)
        if not samples:
            continue
        frames = [frame for _, frame in samples]
        last_frame_time = samples[-1][0]

        inference_started_at = time.time()
        try:
            # @claude vlm_proc.infer() respawns a crashed child on its own; a
            # @claude failure here (incl. switch+rollback both failed) just skips.
            raw = vlm_proc.infer(frames, app_state.get_prompt())
        except Exception as e:
            log.error("VLM inference error: %s", e)
            continue
        inference_elapsed_ms = int(round((time.time() - inference_started_at) * 1000))

        triggers = app_state.get_triggers()
        raw_lower = raw.lower()
        matched = [kw for kw in triggers if kw in raw_lower] if triggers else []
        event_triggered = len(matched) > 0

        if event_triggered:
            event_time = time.time()
            frame_to_event_ms = int(round((event_time - last_frame_time) * 1000))
            log.info(
                "%dms inference, frame_to_event_ms=%d -> EVENT: %s",
                inference_elapsed_ms,
                frame_to_event_ms,
                matched,
            )
        else:
            log.info("%dms -> normal", inference_elapsed_ms)

        app_state.update_inference(
            "EVENT" if event_triggered else "정상",
            raw, inference_elapsed_ms,
            event_triggered=event_triggered)

        if event_triggered:
            threading.Thread(
                target=notify_event,
                args=(matched, raw, event_time, last_frame_time, inference_started_at, inference_elapsed_ms),
                daemon=True,
            ).start()


# ── GStreamer pipeline ───────────────────────────────────────────────────────

def build_pipeline_str(url: str, target_fps: float) -> str:
    """
    Build the pipeline string. `videorate` normalizes to target_fps so
    frame extraction is evenly spaced regardless of the source camera's
    native FPS.

    @claude
    """
    fps = Fraction(target_fps).limit_denominator(1000)
    return (
        f'rtspsrc location={url} latency=0 protocols=tcp '
        '! rtph264depay ! h264parse ! nvv4l2decoder '
        '! nvvidconv ! video/x-raw,format=RGBA '
        f'! videorate ! video/x-raw,framerate={fps.numerator}/{fps.denominator} '
        '! appsink name=sink emit-signals=true sync=false drop=true max-buffers=1'
    )


def make_frame_callback(ring: RingBuffer, infer_queue: queue.Queue):
    """
    Build the `new-sample` signal callback for appsink.
      - RGBA buffer -> numpy -> PIL (384x384 RGB) -> RingBuffer push
      - Signal the inference queue; drop when full (previous inference
        still running).

    @claude
    """
    def on_new_sample(sink) -> Gst.FlowReturn:
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR

        buf = sample.get_buffer()
        caps = sample.get_caps()
        s = caps.get_structure(0)
        w = s.get_value('width')
        h = s.get_value('height')

        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            log.error("buffer.map() failed")
            return Gst.FlowReturn.ERROR

        try:
            arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(h, w, 4)
            img = Image.fromarray(arr[:, :, :3], mode='RGB').resize(VLM_INPUT_SIZE)
        except Exception as e:
            log.error("frame conversion failed: %s", e)
            return Gst.FlowReturn.OK
        finally:
            buf.unmap(map_info)

        captured_at = time.time()
        global _last_frame_time
        _last_frame_time = captured_at
        ring.push(img, captured_at)
        app_state.update_frame(img, w, h)

        try:
            infer_queue.put_nowait(True)
        except queue.Full:
            pass

        return Gst.FlowReturn.OK

    return on_new_sample


# ── Pipeline management ──────────────────────────────────────────────────────

_pipeline = None
_pipeline_lock = threading.Lock()
_pipeline_started_at: float = 0.0
_last_frame_time: float = 0.0

_pipeline_lifecycle = PipelineLifecycle(app_state, lambda: app_state.is_analysis_active())

# @claude Watchdog parameters. The watchdog doubles as the FR-046 stream-connect
# @claude retry: while the streamer has nothing to redistribute yet, the pipeline
# @claude produces no frames and is restarted on this cadence until frames flow.
WATCHDOG_GRACE    = 15.0   # @claude Grace period after PLAYING before we complain about missing frames.
WATCHDOG_TIMEOUT  = 15.0   # @claude Restart if no frames arrive for this long after the last one.
WATCHDOG_INTERVAL = 5.0    # @claude Check interval.


def start_pipeline(ring: RingBuffer, infer_q: queue.Queue, reason: str = "startup", restart: bool = False) -> None:
    """(Re)start the GStreamer pipeline. Stops and replaces any existing one. @claude"""
    global _pipeline, _pipeline_started_at, _last_frame_time
    with _pipeline_lock:
        if _pipeline is not None:
            _pipeline.set_state(Gst.State.NULL)
            log.info("Pipeline stopped (restart)")
            _pipeline = None

        pipeline_str = build_pipeline_str(MEDIAMTX_URL, TARGET_FPS)
        log.info("Pipeline: %s", pipeline_str)

        _pipeline = Gst.parse_launch(pipeline_str)
        sink = _pipeline.get_by_name('sink')
        sink.connect('new-sample', make_frame_callback(ring, infer_q))

        _pipeline.set_state(Gst.State.PLAYING)
        now = time.time()
        _pipeline_started_at = now
        _last_frame_time = now
        app_state.mark_pipeline_starting(reason, restart=restart, started_at=now)
        log.info("Pipeline PLAYING")


def start_analysis() -> bool:
    """Start or restart analysis on the router's request (FR-024). @claude"""
    return _pipeline_lifecycle.request_restart(start_pipeline, "analysis_start")


def stop_analysis() -> None:
    """Stop analysis on the router's request (FR-049, FR-051): tear down the
    pipeline and go idle. The VLM child stays loaded (NFR-023); the watchdog
    idles while no pipeline exists. The caller has already dropped the
    analysis-active flag. @claude"""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            _pipeline.set_state(Gst.State.NULL)
            _pipeline = None
            log.info("Pipeline stopped (analysis_stop)")
    _pipeline_lifecycle.mark_waiting_for_start()


WATCHDOG_TIMEOUT_MAX = 60.0  # @claude Ceiling for the escalating retry interval (FR-046).


def watchdog_worker() -> None:
    """
    Auto-restart the pipeline if no frames have arrived for a while after
    PLAYING — this covers both mid-run stalls and the startup case where
    the redistribution has not begun yet. While no frame has ever arrived
    the restart interval doubles up to a ceiling, which is the analyzer's
    progressive stream-connect retry (FR-046); once frames flow, the
    interval resets to the base timeout.

    @claude
    """
    log.info("Pipeline watchdog started (grace=%.0fs, timeout=%.0fs)",
             WATCHDOG_GRACE, WATCHDOG_TIMEOUT)
    timeout = WATCHDOG_TIMEOUT
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        with _pipeline_lock:
            active = _pipeline is not None
            started = _pipeline_started_at
            last = _last_frame_time
        if not active:
            continue
        now = time.time()
        if last > started:
            timeout = WATCHDOG_TIMEOUT  # @claude Frames arrived — back to the base cadence.
        if now - started < WATCHDOG_GRACE:
            continue
        if now - last > timeout:
            log.warning(
                "Watchdog: no frames for %.0fs — restarting pipeline",
                now - last,
            )
            if last <= started:
                timeout = min(timeout * 2, WATCHDOG_TIMEOUT_MAX)
            _pipeline_lifecycle.handle_watchdog_timeout(start_pipeline)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    log.info("=== Babycat analyzer start ===")
    log.info("  MEDIAMTX_URL : %s", MEDIAMTX_URL)
    log.info("  VLM_MODELS   : %s", VLM_MODELS)
    log.info("  MODEL_ID     : %s (default)", MODEL_ID)
    log.info("  TARGET_FPS   : %s", TARGET_FPS)
    log.info("  N_FRAMES     : %s", N_FRAMES)
    log.info("  RING_SIZE    : %s", RING_SIZE)

    # @claude Restore the persisted settings (FR-014): prompt, keywords, and
    # @claude whether analysis was running before the restart.
    persisted = settings.load()
    app_state.set_prompt(persisted["prompt"])
    app_state.set_triggers(persisted["keywords"])
    app_state.set_analysis_active(persisted["analysis_active"])
    _pipeline_lifecycle.mark_waiting_for_vlm()
    set_start_analysis_callback(start_analysis)
    set_stop_analysis_callback(stop_analysis)

    # @claude Start the HTTP server immediately so settings can be saved while
    # @claude the VLM is still loading (precompile can take tens of minutes).
    start_server(SERVER_PORT)

    # @claude MLC quantize() symlinks the HF snapshot into /data/models/mlc/dist/models/{MODEL};
    # @claude NanoLLM doesn't mkdir the parent, so the container crashes with FileNotFoundError
    # @claude if the directory is missing. Pre-create it so fresh Jetsons can go from
    # @claude `git clone` to `docker compose up` in one shot.
    Path("/data/models/mlc/dist/models").mkdir(parents=True, exist_ok=True)

    # @claude Publish the candidate model list. The true available list comes back from
    # @claude _precompile_all. State starts at "initializing" and transitions
    # @claude to downloading/compiling inside _precompile_all.
    app_state.set_vlm_models(VLM_MODELS, MODEL_ID)

    # @claude Uncompiled models are built in a subprocess — sequential in-process compiles OOM.
    try:
        available = _precompile_all(VLM_MODELS)
    except Exception as e:
        app_state.set_vlm_state("error", str(e)[:240])
        raise
    app_state.set_vlm_models(available, MODEL_ID)
    _set_available(available)

    log.info("Loading default VLM: %s", MODEL_ID)
    app_state.set_vlm_current_model(MODEL_ID)
    app_state.set_vlm_state("loading")
    t0 = time.time()
    vlm_proc = VlmProcess()
    try:
        vlm_proc.start(MODEL_ID)
    except Exception as e:
        app_state.set_vlm_state("error", str(e)[:240])
        raise
    log.info("Model loaded (%.1fs)", time.time() - t0)
    app_state.set_vlm_state("ready")

    # @claude Carries switch requests from the /vlm/switch handler to the worker.
    holder = ModelHolder(MODEL_ID)
    _set_holder(holder)

    ring    = RingBuffer(maxlen=RING_SIZE)
    infer_q = queue.Queue(maxsize=1)

    # @claude Publish refs for start_analysis (before this point, early calls are a safe no-op).
    _pipeline_lifecycle.set_refs(ring, infer_q)

    # @claude Hand the ring ref to AppState so the SSE snapshot can expose ring fill level.
    app_state.set_refs(ring, RING_SIZE, {
        "target_fps": TARGET_FPS,
        "n_frames":   N_FRAMES,
    })

    worker = threading.Thread(
        target=inference_worker,
        args=(holder, vlm_proc, ring, infer_q),
        daemon=True,
    )
    worker.start()

    threading.Thread(target=watchdog_worker, daemon=True).start()

    Gst.init(None)
    # @claude Analysis starts only on the explicit request (FR-025), or resumes
    # @claude when the persisted state says it was running (FR-014).
    if not _pipeline_lifecycle.ensure_startup_started(start_pipeline):
        log.info("Pipeline deferred — waiting for the analysis start request")

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        log.info("Shutdown signal received")
    finally:
        with _pipeline_lock:
            if _pipeline is not None:
                _pipeline.set_state(Gst.State.NULL)
        app_state.mark_pipeline_stopped("shutdown")
        log.info("Pipeline stopped")
        vlm_proc.stop()
        log.info("VLM child stopped")


if __name__ == '__main__':
    main()

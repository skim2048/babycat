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
import signal
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
from notify import notify_event, notify_inference
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

# @claude Frame extraction rate and frames per inference (SDD §7.2 (1), §8.3).
TARGET_FPS = float(os.getenv("TARGET_FPS", "1.0"))
N_FRAMES   = int(os.getenv("N_FRAMES",   "4"))

# @claude Minimum seconds between inference starts (FR-058). 0 = natural pacing
# @claude (the hardware's own inference duration sets the cycle). A floor trades
# @claude event-detection latency for power/heat and history volume; aggregates
# @claude stay comparable across devices because /summary carries per-bucket
# @claude totals as the denominator.
MIN_INFER_INTERVAL = float(os.getenv("MIN_INFER_INTERVAL", "0"))

# @claude Ring capacity in frames: 30 s of context at 1 fps, well above any
# @claude N_FRAMES in use. Fixed — the ring only needs to be larger than N_FRAMES.
RING_SIZE = 30

# @claude Internal port, fixed by compose service URLs (SDD §6.3).
SERVER_PORT = 8080

# @claude Frames are resized to the VLM's SigLIP input size before they enter
# @claude the ring: the model would resize anyway, and doing it here keeps the
# @claude ring and the IPC payload to the child small. Non-square frames are
# @claude squashed, not cropped (SDD §5.1).
VLM_INPUT_SIZE = (384, 384)

# @claude Consecutive inference failures (child respawn included) before the
# @claude process exits and lets the container restart policy take over
# @claude (SDD §7.5).
MAX_CONSECUTIVE_INFER_FAILURES = 3


# ── Ring buffer ──────────────────────────────────────────────────────────────

class RingBuffer:
    """
    Fixed-size circular buffer for VLM context frames. Pushed from the
    GStreamer callback thread and read via latest_samples() from the
    inference thread.

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

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

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

    def request_switch(self, name: str) -> None:
        """Queue a switch. Validation against the available models is the
        caller's (holder.request_switch) — one criterion, one place. @claude"""
        with self._lock:
            if name == self.name and self._switch_to is None:
                return  # @claude Already the active model — nothing to do.
            self._switch_to = name

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
    compile, raise RuntimeError — booting is pointless without it. A
    secondary model that fails is logged and left out of the list.

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
    last_infer_at = 0.0
    failures = 0
    while True:
        # @claude Handle pending switch requests at the boundary between inferences.
        target = holder.pop_request()
        if target and target != holder.name:
            _perform_switch(holder, vlm_proc, target)

        try:
            infer_queue.get(timeout=5)
        except queue.Empty:
            continue

        # @claude A signal that survived a stop must not start an inference.
        if not app_state.is_analysis_active():
            continue

        # @claude Enforce the inference-interval floor: frame signals inside the
        # @claude window are dropped, so the cycle is max(natural, MIN_INFER_INTERVAL).
        if MIN_INFER_INTERVAL > 0 and time.time() - last_infer_at < MIN_INFER_INTERVAL:
            continue

        samples = ring.latest_samples(N_FRAMES)
        if not samples:
            continue
        frames = [frame for _, frame in samples]
        last_frame_time = samples[-1][0]

        # @claude Prompt and keywords are both read at inference start, so a
        # @claude settings change mid-inference cannot pair an old prompt's
        # @claude text with new keywords — one consistent snapshot per cycle.
        # @claude The active preset is resolved here too, so a preset boundary
        # @claude only takes effect between inferences, never mid-generation.
        prompt = app_state.get_prompt()
        triggers = app_state.get_triggers()
        label_groups = app_state.get_label_groups()
        preset = settings.resolve_preset(app_state.get_presets())
        preset_id = "default"
        if preset is not None:
            preset_id = preset["id"]
            prompt = preset.get("prompt", prompt)
            if preset.get("labels") is not None:
                label_groups = preset["labels"]
        app_state.set_active_preset(preset_id)

        inference_started_at = time.time()
        last_infer_at = inference_started_at
        try:
            # @claude vlm_proc.infer() respawns a crashed child on its own.
            raw = vlm_proc.infer(frames, prompt)
        except Exception as e:
            failures += 1
            log.error("VLM inference error (%d/%d): %s", failures, MAX_CONSECUTIVE_INFER_FAILURES, e)
            if failures >= MAX_CONSECUTIVE_INFER_FAILURES:
                # @claude Persistent failure: give up and let the container
                # @claude restart policy bring a clean process up (SDD §7.5).
                app_state.set_vlm_state("error", f"inference failed {failures} times: {str(e)[:160]}")
                log.critical("VLM inference failing persistently — exiting for a container restart")
                os.kill(os.getpid(), signal.SIGTERM)
                return
            continue
        failures = 0
        inference_elapsed_ms = int(round((time.time() - inference_started_at) * 1000))

        # @claude Stop discards in-flight work (SDD §7.3): a judgment that
        # @claude finishes after /stop surfaces nowhere — no state update, no
        # @claude event, no clip minutes after the user stopped analysis.
        if not app_state.is_analysis_active():
            log.info("Inference result discarded (analysis stopped)")
            continue

        raw_lower = raw.lower()
        matched = [kw for kw in triggers if kw in raw_lower] if triggers else []
        event_triggered = len(matched) > 0

        # @claude layer-2 label match: a label hits when any of its synonyms appears
        # @claude in the text. Labels and synonyms are opaque client strings —
        # @claude same substring mechanism as the trigger keywords above.
        matched_labels = [
            label for label, syns in label_groups.items()
            if any(s in raw_lower for s in syns)
        ]

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

        app_state.update_inference(raw, inference_elapsed_ms, event_triggered=event_triggered)

        if event_triggered:
            threading.Thread(
                target=notify_event,
                args=(matched, raw, event_time, last_frame_time, inference_started_at, inference_elapsed_ms),
                daemon=True,
            ).start()

        # @claude layer 1: every inference — matched or not — goes into the history
        # @claude (FR pending). Separate from the event path above, which keeps its
        # @claude clip-recording semantics untouched.
        threading.Thread(
            target=notify_inference,
            args=(time.time(), raw, matched_labels, preset_id,
                  holder.name, inference_elapsed_ms),
            daemon=True,
        ).start()


# ── GStreamer pipeline ───────────────────────────────────────────────────────

SOURCE_PROTOCOL = "rtsp"
SOURCE_TRANSPORT = "tcp"  # @claude rtspsrc protocols=; reported in the SSE snapshot.


def build_pipeline_str(url: str, target_fps: float) -> str:
    """
    Build the pipeline string. `videorate` normalizes to target_fps so
    frame extraction is evenly spaced regardless of the source camera's
    native FPS.

    @claude
    """
    fps = Fraction(target_fps).limit_denominator(1000)
    return (
        f'rtspsrc location={url} latency=0 protocols={SOURCE_TRANSPORT} '
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
_start_lock = threading.Lock()
_pipeline_started_at: float = 0.0
_last_frame_time: float = 0.0

_pipeline_lifecycle = PipelineLifecycle(app_state, lambda: app_state.is_analysis_active())

# @claude Watchdog parameters. The watchdog doubles as the FR-046 stream-connect
# @claude retry: while the streamer has nothing to redistribute yet, the pipeline
# @claude produces no frames and is restarted on this cadence until frames flow.
WATCHDOG_GRACE    = 15.0   # @claude Grace period after PLAYING before we complain about missing frames.
WATCHDOG_TIMEOUT  = 15.0   # @claude Restart if no frames arrive for this long after the last one.
WATCHDOG_INTERVAL = 5.0    # @claude Check interval.


def start_pipeline(ring: RingBuffer, infer_q: queue.Queue, reason: str = "startup") -> None:
    """(Re)start the GStreamer pipeline. Stops and replaces any existing one;
    the state is reported as a restart only when a pipeline was running. @claude"""
    global _pipeline, _pipeline_started_at, _last_frame_time
    # @claude _start_lock serializes whole (re)starts against each other;
    # @claude _pipeline_lock only guards the reference and is never held
    # @claude across set_state(NULL), which can block for a long time on a
    # @claude broken pipeline — holding it there starved /stop into the
    # @claude router's timeout (observed 2026-08-27).
    with _start_lock:
        with _pipeline_lock:
            old = _pipeline
            _pipeline = None
        restart = old is not None
        if old is not None:
            old.set_state(Gst.State.NULL)
            log.info("Pipeline stopped (restart)")

        with _pipeline_lock:
            # @claude Stop wins: /stop drops the active flag before tearing down,
            # @claude so a watchdog restart or a stale start callback that lost the
            # @claude race must not revive the pipeline (FR-049, FR-051). Only a
            # @claude new start request — which sets the flag first — passes here.
            if not app_state.is_analysis_active():
                log.info("Pipeline start skipped (%s): analysis is not active", reason)
                return

            # @claude Inference sees only frames this pipeline extracted (SDD §7.2):
            # @claude frames left from a previous pipeline — an older moment, or an
            # @claude older camera after a profile switch — must never feed a
            # @claude judgment. Clearing at start covers stop/start, watchdog
            # @claude restarts, and profile-switch restarts with one rule.
            ring.clear()
            try:
                infer_q.get_nowait()
            except queue.Empty:
                pass

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
    return _pipeline_lifecycle.request_start(start_pipeline, "analysis_start")


def stop_analysis() -> None:
    """Stop analysis on the router's request (FR-049, FR-051): tear down the
    pipeline and go idle. The VLM child stays loaded (NFR-023); the watchdog
    idles while no pipeline exists. The caller has already dropped the
    analysis-active flag. @claude"""
    global _pipeline
    with _pipeline_lock:
        # @claude Latest flag wins, in both directions (SDD §7.3): if the flag
        # @claude is active again, a newer start owns the pipeline and this
        # @claude stale stop must not tear it down — the mirror of the guard
        # @claude in start_pipeline.
        if app_state.is_analysis_active():
            return
        old = _pipeline
        _pipeline = None
    # @claude Tear down outside the lock: NULL on a broken pipeline can block,
    # @claude and nothing else references the detached object.
    if old is not None:
        old.set_state(Gst.State.NULL)
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
            try:
                _pipeline_lifecycle.handle_watchdog_timeout(start_pipeline)
            except Exception as e:
                # @claude Same protection as the startup path: an unbuildable
                # @claude pipeline surfaces as idle/start_failed, not a dead
                # @claude watchdog or a dead process.
                log.error("watchdog pipeline restart failed: %s", e)
                app_state.mark_pipeline_idle(f"start_failed: {str(e)[:160]}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    Gst.init(None)  # @claude Before the HTTP server: /start may build a pipeline at any time.

    log.info("=== Babycat analyzer start ===")
    log.info("  MEDIAMTX_URL : %s", MEDIAMTX_URL)
    log.info("  VLM_MODELS   : %s", VLM_MODELS)
    log.info("  MODEL_ID     : %s (default)", MODEL_ID)
    log.info("  TARGET_FPS   : %s", TARGET_FPS)
    log.info("  N_FRAMES     : %s", N_FRAMES)
    log.info("  RING_SIZE    : %s", RING_SIZE)
    log.info("  MIN_INFER_INTERVAL : %ss", MIN_INFER_INTERVAL)

    # @claude Restore the persisted settings (FR-014): prompt, keywords, and
    # @claude whether analysis was running before the restart.
    persisted = settings.load()
    app_state.set_prompt(persisted["prompt"])
    app_state.set_triggers(persisted["keywords"])
    app_state.set_label_groups(persisted["labels"])
    app_state.set_presets(persisted["presets"])
    app_state.set_analysis_active(persisted["analysis_active"])
    _pipeline_lifecycle.mark_waiting_for_vlm()
    set_start_analysis_callback(start_analysis)
    set_stop_analysis_callback(stop_analysis)

    # @claude Start the HTTP server immediately so settings can be saved while
    # @claude the VLM is still loading (precompile can take tens of minutes).
    start_server(SERVER_PORT)

    # @claude Base-image dependency (SDD §8.2): MLC quantize() symlinks the HF
    # @claude snapshot into /data/models/mlc/dist/models/{MODEL} and NanoLLM
    # @claude does not mkdir the parent — pre-create it or a fresh volume crashes
    # @claude with FileNotFoundError.
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

    # @claude Publish refs for start_analysis. Before this point a /start only
    # @claude records the active flag; ensure_startup_started below acts on it.
    _pipeline_lifecycle.set_refs(ring, infer_q)
    app_state.set_source(SOURCE_PROTOCOL, SOURCE_TRANSPORT)
    # @claude cfg_min_infer_interval is a client-facing SSE field (FR-058): the
    # @claude effective pacing floor, so a client can confirm the deployed value.
    app_state.set_config({"min_infer_interval": MIN_INFER_INTERVAL})

    worker = threading.Thread(
        target=inference_worker,
        args=(holder, vlm_proc, ring, infer_q),
        daemon=True,
    )
    worker.start()

    threading.Thread(target=watchdog_worker, daemon=True).start()

    # @claude Analysis starts only on the explicit request (FR-025), or resumes
    # @claude when the persisted state says it was running (FR-014).
    # @claude A pipeline that cannot be built (e.g. a missing GStreamer element)
    # @claude must not kill the process — that put the analyzer into a
    # @claude restart-and-reload loop (observed 2026-08-27). The active flag
    # @claude stays set, so a later /start retries after the host is fixed.
    try:
        if not _pipeline_lifecycle.ensure_startup_started(start_pipeline):
            log.info("Pipeline deferred — waiting for the analysis start request")
    except Exception as e:
        log.error("startup pipeline start failed: %s", e)
        app_state.mark_pipeline_idle(f"start_failed: {str(e)[:160]}")

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

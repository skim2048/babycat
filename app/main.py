"""
Babycat — app entry point.

Pipeline:
  rtspsrc (MediaMTX) -> rtph264depay -> h264parse -> nvv4l2decoder
  -> nvvidconv (RGBA) -> videorate -> appsink
  -> RingBuffer -> VLM inference -> keyword match -> trigger clip recording

@claude
"""

import gc
import logging
import os
import queue
import shutil
import subprocess
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
from nano_llm import NanoLLM, ChatHistory

import camera
from clip_storage import (
    ClipStoragePolicy,
    bytes_to_mb,
    cleanup_partial_outputs,
    ensure_clip_capacity,
)
from state import state as app_state
from server import set_restart_pipeline_callback, start_server
from ptz import is_moving as ptz_is_moving
from pipeline_lifecycle import PipelineLifecycle
from trigger_clip_diagnostics import (
    build_trigger_clip_meta,
    probe_clip_duration_seconds,
    summarize_ffmpeg_stderr,
)
from trigger_clip_rollover import (
    bool_env,
    ensure_segment_dir,
    latest_segment_age_seconds,
    list_segments,
    purge_old_segments,
    segment_recorder_cmd,
    select_segments_for_window,
    write_concat_manifest,
)

log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://babycat-mediamtx:8554/live")

# @claude VLM_MODELS / holder singletons live in a dedicated module to avoid the
# @claude double-import trap caused by main.py being loaded both as __main__ and as `main`.
from holder import VLM_MODELS, set_holder as _set_holder, set_available as _set_available
MODEL_ID = VLM_MODELS[0]

TARGET_FPS = float(os.getenv("TARGET_FPS", "1.0"))
N_FRAMES   = int(os.getenv("N_FRAMES",   "4"))

RING_SIZE = int(os.getenv("RING_SIZE", "30"))

TRIGGER_COOLDOWN  = float(os.getenv("TRIGGER_COOLDOWN", "30"))
TRIGGER_CLIP_DUR  = int(os.getenv("TRIGGER_CLIP_DUR", "5"))
CLIP_MIN_FREE_MB = int(os.getenv("CLIP_MIN_FREE_MB", "256"))
CLIP_TARGET_FREE_MB = int(os.getenv("CLIP_TARGET_FREE_MB", "512"))
CLIP_PRUNE_MAX_FILES = int(os.getenv("CLIP_PRUNE_MAX_FILES", "20"))
TRIGGER_ROLLOVER_ENABLED = bool_env("TRIGGER_ROLLOVER_ENABLED", False)
TRIGGER_SEGMENT_DIR = os.getenv("TRIGGER_SEGMENT_DIR", "/data/.segments/live")
TRIGGER_SEGMENT_TIME = int(os.getenv("TRIGGER_SEGMENT_TIME", "1"))
TRIGGER_SEGMENT_RETENTION = int(os.getenv("TRIGGER_SEGMENT_RETENTION", "15"))
TRIGGER_PRE_EVENT_SEC = float(os.getenv("TRIGGER_PRE_EVENT_SEC", "2"))
TRIGGER_POST_EVENT_SEC = float(os.getenv("TRIGGER_POST_EVENT_SEC", str(TRIGGER_CLIP_DUR)))

# @claude SigLIP input resolution; the VLM resizes to 384x384 internally.
VLM_INPUT_SIZE = (384, 384)

INFERENCE_PROMPT_DEFAULT = "What is the person doing? Answer in one sentence."

 
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

    def push(self, frame: Image.Image) -> None:
        with self._lock:
            self._buf.append(frame)

    def latest(self, n: int) -> list:
        """Return the most recent n frames (fewer if the buffer has less). @claude"""
        with self._lock:
            frames = list(self._buf)
        return frames[-n:] if len(frames) >= n else frames

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


# ── Trigger clip recording ───────────────────────────────────────────────────

_trigger_last_save: float = 0.0
_trigger_lock = threading.Lock()
CLIP_STORAGE_POLICY = ClipStoragePolicy(
    min_free_bytes=max(0, CLIP_MIN_FREE_MB) * 1024 * 1024,
    target_free_bytes=max(CLIP_MIN_FREE_MB, CLIP_TARGET_FREE_MB) * 1024 * 1024,
    prune_max_files=max(0, CLIP_PRUNE_MAX_FILES),
)
_segment_recorder_started = False
_segment_recorder_lock = threading.Lock()


def _finalize_rollover_clip(
    matched_keywords: list[str],
    vlm_text: str,
    event_time: float,
    *,
    clip_dir: str,
) -> bool:
    window_start = event_time - TRIGGER_PRE_EVENT_SEC
    window_end = event_time + TRIGGER_POST_EVENT_SEC
    wait_seconds = max(0.0, window_end - time.time())
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    record_requested_at = time.time()
    lt = time.localtime(event_time)
    ts = time.strftime("%Y%m%d_%H%M%S", lt)
    ms = int((event_time - int(event_time)) * 1000)
    base = f"{ts}_{ms:03d}"

    dest_dir = Path(clip_dir) / time.strftime("%Y", lt) / time.strftime("%m", lt)
    dest_dir.mkdir(parents=True, exist_ok=True)

    capacity = ensure_clip_capacity(clip_dir, CLIP_STORAGE_POLICY)
    if capacity.deleted_files:
        log.warning(
            "trigger-clip pruned %d old clips to recover %.1f MB (free=%d MB)",
            capacity.deleted_files,
            capacity.deleted_bytes / (1024 * 1024),
            bytes_to_mb(capacity.free_bytes) or 0,
        )
    if not capacity.ok:
        free_mb = bytes_to_mb(capacity.free_bytes)
        log.warning(
            "trigger-clip skipped: low disk space before finalize (free=%d MB, min=%d MB, deleted=%d)",
            free_mb or 0,
            CLIP_MIN_FREE_MB,
            capacity.deleted_files,
        )
        app_state.invalidate_clip_cache()
        app_state.set_clip_storage_status("skipped", capacity.reason, free_mb)
        return False

    selected_segments = select_segments_for_window(
        TRIGGER_SEGMENT_DIR,
        window_start,
        window_end,
        segment_span_s=TRIGGER_SEGMENT_TIME,
    )
    if not selected_segments:
        free_mb = bytes_to_mb(shutil.disk_usage(dest_dir).free)
        log.error(
            "trigger-clip finalize failed: no rollover segments for %s (window_start=%.3f, window_end=%.3f)",
            base,
            window_start,
            window_end,
        )
        app_state.set_clip_storage_status("error", "segment_window_empty", free_mb)
        return False

    out_path = dest_dir / f"{base}.mp4"
    meta_path = dest_dir / f"{base}.json"
    manifest_path = Path(TRIGGER_SEGMENT_DIR) / f"{base}.segments.txt"
    write_concat_manifest(selected_segments, manifest_path)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest_path),
        "-c",
        "copy",
        str(out_path),
    ]
    ffmpeg_started_at = time.time()
    start_delay_ms = int(round((ffmpeg_started_at - event_time) * 1000))
    log.info(
        "trigger-clip finalize start: %s (segments=%d, window_start=%.3f, window_end=%.3f, finalize_delay_ms=%d)",
        out_path.name,
        len(selected_segments),
        window_start,
        window_end,
        start_delay_ms,
    )
    try:
        run_started_at = time.time()
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=int(TRIGGER_PRE_EVENT_SEC + TRIGGER_POST_EVENT_SEC + 15),
            check=False,
        )
        ffmpeg_elapsed_ms = int(round((time.time() - run_started_at) * 1000))
        stderr_summary = summarize_ffmpeg_stderr(result.stderr)
        if result.returncode != 0:
            cleanup_partial_outputs(out_path, meta_path)
            free_mb = bytes_to_mb(shutil.disk_usage(dest_dir).free)
            log.error(
                "trigger-clip finalize failed: %s (exit=%d, segments=%d, finalize_delay_ms=%d, ffmpeg_elapsed_ms=%d, stderr=%r)",
                out_path.name,
                result.returncode,
                len(selected_segments),
                start_delay_ms,
                ffmpeg_elapsed_ms,
                stderr_summary,
            )
            app_state.set_clip_storage_status("error", "ffmpeg_failed", free_mb)
            return False
        clip_size_bytes = out_path.stat().st_size if out_path.exists() else 0
        clip_duration_s = probe_clip_duration_seconds(out_path)
        log.info(
            "trigger-clip finalize done: %s (segments=%d, finalize_delay_ms=%d, ffmpeg_elapsed_ms=%d, clip_size_bytes=%d, clip_duration_s=%s)",
            out_path.name,
            len(selected_segments),
            start_delay_ms,
            ffmpeg_elapsed_ms,
            clip_size_bytes,
            clip_duration_s if clip_duration_s is not None else "unknown",
        )
    except subprocess.TimeoutExpired:
        log.warning("trigger-clip finalize timeout: %s", out_path.name)
        cleanup_partial_outputs(out_path, meta_path)
        app_state.set_clip_storage_status("error", "ffmpeg_timeout", bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return False
    except Exception as e:
        log.error("trigger-clip finalize error: %s", e)
        cleanup_partial_outputs(out_path, meta_path)
        app_state.set_clip_storage_status("error", "ffmpeg_error", bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return False
    finally:
        try:
            manifest_path.unlink()
        except OSError:
            pass

    try:
        import json as _json

        meta = build_trigger_clip_meta(
            event_time=event_time,
            matched_keywords=matched_keywords,
            vlm_text=vlm_text,
            record_requested_at=record_requested_at,
            ffmpeg_started_at=ffmpeg_started_at,
            ffmpeg_elapsed_ms=ffmpeg_elapsed_ms,
            clip_size_bytes=clip_size_bytes,
            clip_duration_s=clip_duration_s,
        )
        meta.update({
            "record_mode": "segment_rollover",
            "segment_window_start_ms": int(round(window_start * 1000)),
            "segment_window_end_ms": int(round(window_end * 1000)),
            "selected_segment_count": len(selected_segments),
            "capture_source": "mediamtx_rollover_segments",
            "video_codec_mode": "copy_concat",
        })
        with open(meta_path, "w", encoding="utf-8") as f:
            _json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("metadata save error: %s", e)

    app_state.invalidate_clip_cache()
    app_state.set_clip_storage_status(
        "ok",
        capacity.reason if capacity.reason != "ok" else "",
        bytes_to_mb(shutil.disk_usage(dest_dir).free),
    )
    return True


def _record_direct_trigger_clip(
    matched_keywords: list[str],
    vlm_text: str,
    event_time: float,
    *,
    clip_dir: str,
) -> bool:
    """Record a trigger clip directly from the RTSP source via ffmpeg."""
    record_requested_at = time.time()
    lt = time.localtime(event_time)
    ts = time.strftime("%Y%m%d_%H%M%S", lt)
    ms = int((event_time - int(event_time)) * 1000)
    base = f"{ts}_{ms:03d}"

    import json as _json
    dest_dir = Path(clip_dir) / time.strftime("%Y", lt) / time.strftime("%m", lt)
    dest_dir.mkdir(parents=True, exist_ok=True)

    capacity = ensure_clip_capacity(clip_dir, CLIP_STORAGE_POLICY)
    if capacity.deleted_files:
        log.warning(
            "trigger-clip pruned %d old clips to recover %.1f MB (free=%d MB)",
            capacity.deleted_files,
            capacity.deleted_bytes / (1024 * 1024),
            bytes_to_mb(capacity.free_bytes) or 0,
        )
    if not capacity.ok:
        free_mb = bytes_to_mb(capacity.free_bytes)
        log.warning(
            "trigger-clip skipped: low disk space (free=%d MB, min=%d MB, deleted=%d)",
            free_mb or 0,
            CLIP_MIN_FREE_MB,
            capacity.deleted_files,
        )
        app_state.invalidate_clip_cache()
        app_state.set_clip_storage_status("skipped", capacity.reason, free_mb)
        return False

    out_path = dest_dir / f"{base}.mp4"
    meta_path = dest_dir / f"{base}.json"

    cmd = [
        "ffmpeg", "-y",
        "-rtsp_transport", "tcp",
        "-i", MEDIAMTX_URL,
        "-t", str(TRIGGER_CLIP_DUR),
        "-c:v", "copy", "-c:a", "aac",
        str(out_path),
    ]
    ffmpeg_started_at = time.time()
    start_delay_ms = int(round((ffmpeg_started_at - event_time) * 1000))
    log.info(
        "trigger-clip recording start: %s (%ds, event_time=%.3f, start_delay_ms=%d)",
        out_path.name,
        TRIGGER_CLIP_DUR,
        event_time,
        start_delay_ms,
    )
    try:
        run_started_at = time.time()
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=TRIGGER_CLIP_DUR + 10,
            check=False,
        )
        ffmpeg_elapsed_ms = int(round((time.time() - run_started_at) * 1000))
        stderr_summary = summarize_ffmpeg_stderr(result.stderr)
        if result.returncode != 0:
            cleanup_partial_outputs(out_path, meta_path)
            free_mb = bytes_to_mb(shutil.disk_usage(dest_dir).free)
            log.error(
                "trigger-clip recording failed: %s (exit=%d, start_delay_ms=%d, ffmpeg_elapsed_ms=%d, stderr=%r)",
                out_path.name,
                result.returncode,
                start_delay_ms,
                ffmpeg_elapsed_ms,
                stderr_summary,
            )
            app_state.set_clip_storage_status("error", "ffmpeg_failed", free_mb)
            return False
        clip_size_bytes = out_path.stat().st_size if out_path.exists() else 0
        clip_duration_s = probe_clip_duration_seconds(out_path)
        log.info(
            "trigger-clip recording done: %s (start_delay_ms=%d, ffmpeg_elapsed_ms=%d, clip_size_bytes=%d, clip_duration_s=%s)",
            out_path.name,
            start_delay_ms,
            ffmpeg_elapsed_ms,
            clip_size_bytes,
            clip_duration_s if clip_duration_s is not None else "unknown",
        )
    except subprocess.TimeoutExpired:
        log.warning("trigger-clip recording timeout: %s", out_path.name)
        cleanup_partial_outputs(out_path, meta_path)
        app_state.set_clip_storage_status("error", "ffmpeg_timeout", bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return False
    except Exception as e:
        log.error("trigger-clip recording error: %s", e)
        cleanup_partial_outputs(out_path, meta_path)
        app_state.set_clip_storage_status("error", "ffmpeg_error", bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return False

    try:
        meta = build_trigger_clip_meta(
            event_time=event_time,
            matched_keywords=matched_keywords,
            vlm_text=vlm_text,
            record_requested_at=record_requested_at,
            ffmpeg_started_at=ffmpeg_started_at,
            ffmpeg_elapsed_ms=ffmpeg_elapsed_ms,
            clip_size_bytes=clip_size_bytes,
            clip_duration_s=clip_duration_s,
        )
        meta.update({
            "record_mode": "direct_rtsp_record",
            "capture_source": "mediamtx_rtsp",
            "video_codec_mode": "copy",
        })
        with open(meta_path, "w", encoding="utf-8") as f:
            _json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error("metadata save error: %s", e)

    app_state.invalidate_clip_cache()
    app_state.set_clip_storage_status(
        "ok",
        capacity.reason if capacity.reason != "ok" else "",
        bytes_to_mb(shutil.disk_usage(dest_dir).free),
    )
    return True


def _segment_recorder_worker() -> None:
    segment_dir = ensure_segment_dir(TRIGGER_SEGMENT_DIR)
    app_state.set_segment_recorder_status("starting", segment_count=0, last_segment_age_s=None)
    log.info(
        "segment-recorder enabled: dir=%s segment_time=%ss retention=%ss pre=%.1fs post=%.1fs",
        segment_dir,
        TRIGGER_SEGMENT_TIME,
        TRIGGER_SEGMENT_RETENTION,
        TRIGGER_PRE_EVENT_SEC,
        TRIGGER_POST_EVENT_SEC,
    )
    backoff = 1.0
    while True:
        retain_since = time.time() - TRIGGER_SEGMENT_RETENTION
        purge_old_segments(segment_dir, retain_since=retain_since)
        cmd = segment_recorder_cmd(MEDIAMTX_URL, segment_dir, segment_time_s=TRIGGER_SEGMENT_TIME)
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            log.error("segment-recorder launch failed: %s", e)
            app_state.set_segment_recorder_status("error", error=str(e)[:240], segment_count=0, last_segment_age_s=None)
            time.sleep(backoff)
            backoff = min(backoff * 2, 10.0)
            continue

        log.info("segment-recorder started")
        app_state.set_segment_recorder_status("running", error="")
        while True:
            if proc.poll() is not None:
                break
            purge_old_segments(segment_dir, retain_since=time.time() - TRIGGER_SEGMENT_RETENTION)
            app_state.set_segment_recorder_status(
                "running",
                error="",
                segment_count=len(list_segments(segment_dir)),
                last_segment_age_s=latest_segment_age_seconds(segment_dir),
            )
            time.sleep(1.0)

        try:
            _, stderr = proc.communicate(timeout=1)
        except Exception:
            stderr = b""
        log.warning(
            "segment-recorder exited: exit=%d stderr=%r",
            proc.returncode,
            summarize_ffmpeg_stderr(stderr),
        )
        app_state.set_segment_recorder_status(
            "error",
            error=f"exit={proc.returncode}",
            segment_count=len(list_segments(segment_dir)),
            last_segment_age_s=latest_segment_age_seconds(segment_dir),
        )
        time.sleep(backoff)
        backoff = min(backoff * 2, 10.0)


def start_segment_recorder_once() -> None:
    global _segment_recorder_started
    if not TRIGGER_ROLLOVER_ENABLED:
        app_state.set_segment_recorder_status("disabled", error="", segment_count=0, last_segment_age_s=None)
        return
    with _segment_recorder_lock:
        if _segment_recorder_started:
            return
        threading.Thread(target=_segment_recorder_worker, daemon=True).start()
        _segment_recorder_started = True


def save_trigger_clip(matched_keywords: list[str], vlm_text: str,
                      event_time: float) -> None:
    """
    On a trigger keyword event, finalize a user-visible clip around the
    event from rolling MediaMTX-backed segments. Output path:
      {DATA_DIR}/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4 (+ same-name .json)
    Repeat calls within TRIGGER_COOLDOWN are ignored.

    @claude
    """
    global _trigger_last_save
    with _trigger_lock:
        if event_time - _trigger_last_save < TRIGGER_COOLDOWN:
            return
        _trigger_last_save = event_time

    clip_dir = app_state.get_clip_dir()
    if not clip_dir:
        log.warning("No clip directory set — skipping trigger clip")
        app_state.set_clip_storage_status("skipped", "clip_dir_unset")
        return
    if TRIGGER_ROLLOVER_ENABLED:
        ok = _finalize_rollover_clip(
            matched_keywords,
            vlm_text,
            event_time,
            clip_dir=clip_dir,
        )
        if ok:
            return
        log.warning("trigger-clip rollover failed — falling back to direct RTSP recording")

    _record_direct_trigger_clip(
        matched_keywords,
        vlm_text,
        event_time,
        clip_dir=clip_dir,
    )


# ── VLM model holder (switch support) ────────────────────────────────────────

class ModelHolder:
    """
    Current VLM model plus any pending switch request. The worker checks
    pop_request() at the top of each iteration, so a switch only happens
    between inferences, never mid-generation (atomicity).

    @claude
    """
    def __init__(self, model, name: str):
        self._lock = threading.Lock()
        self.model = model
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


def _load_model(model_id: str):
    """Load via NanoLLM (q4f16_ft MLC). Exceptions bubble up. @claude"""
    return NanoLLM.from_pretrained(model_id, api="mlc", quantization="q4f16_ft")


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
        # @claude If the HF snapshot is missing, _precompile_one downloads first; download
        # @claude takes far longer than compilation, so label the longer phase distinctly.
        # @claude A single subprocess covers both phases so the boundary is approximate (OK by design).
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


def _perform_switch(holder: ModelHolder, target: str) -> None:
    """
    Replace the holder's model with `target`. Assumes any in-flight
    inference has already finished. Attempts to roll back to the previous
    model on failure.

    @claude
    """
    prev = holder.name
    log.info("Switching VLM: %s → %s", prev, target)
    app_state.set_vlm_state("switching")
    app_state.set_vlm_current_model(target)  # @claude Pre-apply the target to the UI so the selector reflects intent.

    holder.model = None
    gc.collect()

    try:
        new_model = _load_model(target)
    except Exception as e:
        log.error("VLM switch failed (%s → %s): %s", prev, target, e)
        app_state.set_vlm_state("error", f"{target}: {str(e)[:200]}")
        # @claude Rollback attempt to the previous model.
        try:
            holder.model = _load_model(prev)
            app_state.set_vlm_current_model(prev)
            app_state.set_vlm_state("ready")
            log.info("Rolled back to %s", prev)
        except Exception as e2:
            log.error("Rollback to %s also failed: %s", prev, e2)
        return

    holder.model = new_model
    holder.name = target
    app_state.set_vlm_state("ready")
    log.info("VLM switch complete: %s", target)


# ── VLM inference ────────────────────────────────────────────────────────────

def run_inference(model: NanoLLM, frames: list) -> str:
    """
    Run VLM inference over a list of PIL frames using the ChatHistory API
    (the correct multimodal entry point for NanoLLM). chat.reset() and
    gc.collect() are mandatory — see NanoLLM GitHub issue #39 on memory
    leaks.

    @claude
    """
    chat = ChatHistory(model)
    for img in frames:
        chat.append('user', image=img)
    chat.append('user', text=app_state.get_prompt())

    embedding, _ = chat.embed_chat()
    tokens = []
    for token in model.generate(embedding, max_new_tokens=32, streaming=True):
        tokens.append(token)

    raw = "".join(tokens)
    # @claude Truncate at any stop token (vicuna-v1 </s>, ChatML <|im_end|>) and at common
    # @claude roleplay artifacts (###, <|im_start|>, assistant:, user:) when they appear.
    for marker in ("<|im_end|>", "</s>", "<|im_start|>", "###", "assistant:", "user:"):
        idx = raw.find(marker)
        if idx >= 0:
            raw = raw[:idx]
    raw = raw.strip()
    chat.reset()
    gc.collect()

    return raw


# ── Inference worker thread ──────────────────────────────────────────────────

def inference_worker(holder: "ModelHolder", ring: RingBuffer,
                     infer_queue: queue.Queue) -> None:
    """
    When the appsink callback signals infer_queue, pull the latest
    N_FRAMES from `ring`, run VLM inference, match keywords, and record a
    trigger clip if needed.

    Each iteration starts by consulting holder.pop_request() so model
    switches are only performed between inferences, never mid-generation.

    @claude
    """
    log.info("VLM inference thread started")
    while True:
        # @claude Handle pending switch requests at the boundary between inferences.
        target = holder.pop_request()
        if target and target != holder.name:
            _perform_switch(holder, target)

        try:
            infer_queue.get(timeout=5)
        except queue.Empty:
            continue

        if ptz_is_moving():
            continue

        if holder.model is None:
            # @claude Both switch and rollback failed — skip this iteration.
            continue

        frames = ring.latest(N_FRAMES)
        if not frames:
            continue

        t0 = time.time()
        try:
            raw = run_inference(holder.model, frames)
        except Exception as e:
            log.error("VLM inference error: %s", e)
            continue
        elapsed_ms = (time.time() - t0) * 1000

        triggers = app_state.get_triggers()
        raw_lower = raw.lower()
        matched = [kw for kw in triggers if kw in raw_lower] if triggers else []
        event_triggered = len(matched) > 0

        if event_triggered:
            log.info("%.0fms -> EVENT: %s", elapsed_ms, matched)
        else:
            log.info("%.0fms -> normal", elapsed_ms)

        app_state.update_inference(
            "EVENT" if event_triggered else "정상",
            raw, elapsed_ms,
            event_triggered=event_triggered)

        if event_triggered:
            threading.Thread(
                target=save_trigger_clip, args=(matched, raw, time.time()), daemon=True
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

        global _last_frame_time
        _last_frame_time = time.time()
        ring.push(img)
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

_pipeline_lifecycle = PipelineLifecycle(app_state, lambda: camera.camera_ready.is_set())

# @claude Watchdog parameters.
WATCHDOG_GRACE    = 15.0   # @claude Grace period after PLAYING before we complain about missing frames (initial RTSP handshake).
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


def restart_pipeline(reason: str = "manual_restart") -> bool:
    """Request a pipeline restart. Returns False when refs are not ready yet. @codex"""
    return _pipeline_lifecycle.request_restart(start_pipeline, reason)


def watchdog_worker() -> None:
    """
    Auto-restart the pipeline if no frames have arrived for a while after
    PLAYING — this recovers from rtspsrc latching onto MediaMTX before
    MediaMTX is ready and then stalling.

    @claude
    """
    log.info("Pipeline watchdog started (grace=%.0fs, timeout=%.0fs)",
             WATCHDOG_GRACE, WATCHDOG_TIMEOUT)
    while True:
        time.sleep(WATCHDOG_INTERVAL)
        with _pipeline_lock:
            active = _pipeline is not None
            started = _pipeline_started_at
            last = _last_frame_time
        if not active:
            continue
        now = time.time()
        if now - started < WATCHDOG_GRACE:
            continue
        if now - last > WATCHDOG_TIMEOUT:
            log.warning(
                "Watchdog: no frames for %.0fs — restarting pipeline",
                now - last,
            )
            _pipeline_lifecycle.handle_watchdog_timeout(start_pipeline)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    log.info("=== Babycat App start ===")
    log.info("  MEDIAMTX_URL : %s", MEDIAMTX_URL)
    log.info("  VLM_MODELS   : %s", VLM_MODELS)
    log.info("  MODEL_ID     : %s (default)", MODEL_ID)
    log.info("  TARGET_FPS   : %s", TARGET_FPS)
    log.info("  N_FRAMES     : %s", N_FRAMES)
    log.info("  RING_SIZE    : %s", RING_SIZE)

    app_state.set_prompt(INFERENCE_PROMPT_DEFAULT)
    app_state.set_clip_dir(camera.DATA_DIR)
    _pipeline_lifecycle.mark_waiting_for_vlm()
    set_restart_pipeline_callback(restart_pipeline)
    start_segment_recorder_once()

    # @claude Start the debug/web server immediately so the web UI can save a camera profile
    # @claude while the VLM is still loading (NanoLLM.from_pretrained can take tens of minutes
    # @claude on a cold model cache).
    start_server(8080)

    # @claude Apply any saved camera config in the background (includes MediaMTX retry).
    threading.Thread(target=camera.startup_apply, daemon=True).start()

    # @claude VLM load takes time. If the user saves a camera profile during loading,
    # @claude camera.apply works, but restart_pipeline() is a no-op while _pipeline_refs is
    # @claude None — after load completes, if camera.camera_ready is set, start_pipeline is
    # @claude invoked once below.
    #
    # @claude MLC quantize() symlinks the HF snapshot into /data/models/mlc/dist/models/{MODEL};
    # @claude NanoLLM doesn't mkdir the parent, so the container crashes with FileNotFoundError
    # @claude if the directory is missing. Pre-create it so fresh Jetsons can go from
    # @claude `git clone` to `docker compose up` in one shot.
    Path("/data/models/mlc/dist/models").mkdir(parents=True, exist_ok=True)

    # @claude Publish the candidate model list. The true available list comes back from
    # @claude _precompile_all. State starts at "initializing" (AppState default) and transitions
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
    # @claude Load the precompiled/downloaded model into memory. "loading" is scoped to
    # @claude this single stage — previously it covered downloading+compiling too, which made
    # @claude the UI look stuck.
    app_state.set_vlm_state("loading")
    t0 = time.time()
    try:
        model = _load_model(MODEL_ID)
    except Exception as e:
        app_state.set_vlm_state("error", str(e)[:240])
        raise
    log.info("Model loaded (%.1fs)", time.time() - t0)
    app_state.set_vlm_state("ready")

    # @claude Shared holder between the inference worker and the /vlm/switch handler.
    holder = ModelHolder(model, MODEL_ID)
    _set_holder(holder)

    ring    = RingBuffer(maxlen=RING_SIZE)
    infer_q = queue.Queue(maxsize=1)

    # @claude Publish refs for restart_pipeline (before this point, early calls are a safe no-op).
    _pipeline_lifecycle.set_refs(ring, infer_q)

    # @claude Hand the ring ref to AppState so the SSE snapshot can expose ring fill level.
    app_state.set_refs(ring, RING_SIZE, {
        "target_fps": TARGET_FPS,
        "n_frames":   N_FRAMES,
    })

    # @claude If no camera config is saved yet, wait for the user's web input (start_server
    # @claude is already up, so the user can save a profile even while the model is loading).
    if not camera.camera_ready.is_set():
        log.info("Waiting for camera config (max 60s)...")
        if camera.camera_ready.wait(timeout=60):
            log.info("Camera config applied")
        else:
            log.info("Camera not configured — pipeline will start when camera is set")
            _pipeline_lifecycle.mark_waiting_for_camera()

    worker = threading.Thread(
        target=inference_worker,
        args=(holder, ring, infer_q),
        daemon=True,
    )
    worker.start()

    threading.Thread(target=watchdog_worker, daemon=True).start()

    Gst.init(None)
    if not _pipeline_lifecycle.ensure_startup_started(start_pipeline):
        log.info("Pipeline deferred — waiting for camera config")

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


if __name__ == '__main__':
    main()

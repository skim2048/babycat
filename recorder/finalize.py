"""
Event clip finalization (FR-030) and history recording (FR-031).

On an event notification, waits out the post-event window, concatenates
the matching tmpfs segments without re-encoding, writes the mp4 + sidecar
pair, and records the history row — all in one procedure so the pair and
the history cannot drift apart (SDD §4.4). Falls back to direct RTSP
recording when no segments cover the window.

@claude
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from clip_storage import (
    ClipStoragePolicy,
    ClipStorageResult,
    bytes_to_mb,
    cleanup_partial_outputs,
    count_added_clip,
    ensure_clip_capacity,
    list_clip_files,
)
from diagnostics import (
    build_trigger_clip_meta,
    probe_clip_duration_seconds,
    summarize_ffmpeg_stderr,
)
from events_db import delete_events_for_clips, insert_event
from rollover import (
    select_segments_for_window,
    write_concat_manifest,
)
from status import status
import state_store

log = logging.getLogger(__name__)

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://streamer:8554/live")
CLIP_DIR = os.getenv("CLIP_DIR", "/data/clips")
SEGMENT_DIR = os.getenv("TRIGGER_SEGMENT_DIR", "/run/babycat-segments/live")
SEGMENT_TIME = int(os.getenv("TRIGGER_SEGMENT_TIME", "1"))

TRIGGER_COOLDOWN = float(os.getenv("TRIGGER_COOLDOWN", "30"))
TRIGGER_CLIP_DUR = int(os.getenv("TRIGGER_CLIP_DUR", "5"))
TRIGGER_PRE_EVENT_SEC = float(os.getenv("TRIGGER_PRE_EVENT_SEC", "2"))
TRIGGER_POST_EVENT_SEC = float(os.getenv("TRIGGER_POST_EVENT_SEC", str(TRIGGER_CLIP_DUR)))

CLIP_MIN_FREE_MB = int(os.getenv("CLIP_MIN_FREE_MB", "512"))
CLIP_TARGET_FREE_MB = int(os.getenv("CLIP_TARGET_FREE_MB", "1024"))

# @claude 1회 정리당 삭제 상한(내부 안전판). 운영자가 조정할 값이 아니므로
# @claude 환경 변수로 노출하지 않고 고정한다.
CLIP_PRUNE_MAX_FILES = 50

CLIP_STORAGE_POLICY = ClipStoragePolicy(
    min_free_bytes=max(0, CLIP_MIN_FREE_MB) * 1024 * 1024,
    target_free_bytes=max(CLIP_MIN_FREE_MB, CLIP_TARGET_FREE_MB) * 1024 * 1024,
    prune_max_files=CLIP_PRUNE_MAX_FILES,
)

# @claude The cooldown anchor survives a restart (FR-030, SDD §5.4): a restart
# @claude in the middle of a persisting situation must not reopen the window.
_trigger_last_save: float = float(state_store.load().get("last_event_accepted_at") or 0.0)
_trigger_lock = threading.Lock()


def accept_event(payload: dict) -> bool:
    """
    Cooldown gate for /notify. When accepted, the finalize worker thread is
    started and the history row is guaranteed to be written (clip_name may
    end up None when every capture path failed).
    """
    global _trigger_last_save
    event_time = float(payload.get("event_time") or time.time())
    with _trigger_lock:
        if event_time - _trigger_last_save < TRIGGER_COOLDOWN:
            return False
        _trigger_last_save = event_time
        state_store.update(last_event_accepted_at=event_time)
    threading.Thread(target=_process_event, args=(payload,), daemon=True).start()
    return True


def _process_event(payload: dict) -> None:
    matched = [str(k) for k in payload.get("keywords") or []]
    vlm_text = str(payload.get("vlm_text") or "")
    event_time = float(payload.get("event_time") or time.time())
    last_frame_time = payload.get("last_frame_time")
    inference_started_at = payload.get("inference_started_at")
    inference_elapsed_ms = payload.get("inference_elapsed_ms")

    clip_name = _finalize_rollover_clip(
        matched, vlm_text, event_time,
        last_frame_time=last_frame_time,
        inference_started_at=inference_started_at,
        inference_elapsed_ms=inference_elapsed_ms,
    )
    if clip_name is None:
        log.warning("rollover finalize failed — falling back to direct RTSP recording")
        clip_name = _record_direct_clip(
            matched, vlm_text, event_time,
            last_frame_time=last_frame_time,
            inference_started_at=inference_started_at,
            inference_elapsed_ms=inference_elapsed_ms,
        )

    # @claude FR-031: the occurrence is recorded even when clip capture failed;
    # @claude a NULL clip_name marks a clipless event. created_at is the
    # @claude judgment moment, formatted like the DB default (UTC ISO 8601).
    insert_event(
        ",".join(matched),
        clip_name,
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(event_time)),
    )


def _prune_with_history(base: str, policy: ClipStoragePolicy) -> ClipStorageResult:
    """FR-033: capacity pruning removes clip+sidecar pairs and their history rows."""
    before = {p.name for p in list_clip_files(base)}
    result = ensure_clip_capacity(base, policy)
    if result.deleted_files:
        after = {p.name for p in list_clip_files(base)}
        removed = sorted(before - after)
        history = delete_events_for_clips(removed)
        log.info(
            "auto-pruned %d clips (%.1f MB) and %d history rows to recover space (NFR-010)",
            result.deleted_files,
            result.deleted_bytes / (1024 * 1024),
            history,
        )
    return result


def _event_base_name(event_time: float) -> tuple[str, Path]:
    lt = time.localtime(event_time)
    ts = time.strftime("%Y%m%d_%H%M%S", lt)
    ms = int((event_time - int(event_time)) * 1000)
    base = f"{ts}_{ms:03d}"
    dest_dir = Path(CLIP_DIR) / time.strftime("%Y", lt) / time.strftime("%m", lt)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return base, dest_dir


def _finalize_rollover_clip(
    matched_keywords: list[str],
    vlm_text: str,
    event_time: float,
    *,
    last_frame_time: float | None = None,
    inference_started_at: float | None = None,
    inference_elapsed_ms: int | None = None,
) -> str | None:
    # @claude The clip window is anchored on the capture time of the last
    # @claude frame the VLM saw, not on the judgment time: judgment lags the
    # @claude scene by the inference latency (seconds on slow boards), and a
    # @claude judgment-anchored window can miss a transient event entirely
    # @claude (SDD §7.2 (5)). Falls back to the judgment time when the
    # @claude notification carries no frame time.
    anchor = float(last_frame_time) if last_frame_time else event_time
    window_start = anchor - TRIGGER_PRE_EVENT_SEC
    window_end = anchor + TRIGGER_POST_EVENT_SEC
    wait_seconds = max(0.0, window_end - time.time())
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    record_requested_at = time.time()
    base, dest_dir = _event_base_name(event_time)

    capacity = _prune_with_history(CLIP_DIR, CLIP_STORAGE_POLICY)
    if not capacity.ok:
        free_mb = bytes_to_mb(capacity.free_bytes)
        log.warning(
            "trigger-clip skipped: low disk space (free=%d MB, min=%d MB)",
            free_mb or 0, CLIP_MIN_FREE_MB,
        )
        status.set_clip_storage("skipped", capacity.reason, free_mb)
        return None

    selected_segments = select_segments_for_window(SEGMENT_DIR, window_start, window_end)
    if not selected_segments:
        log.error("trigger-clip finalize failed: no rollover segments for %s", base)
        status.set_clip_storage("error", "segment_window_empty",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None

    out_path = dest_dir / f"{base}.mp4"
    # @claude Atomic publish (SDD §5.4): ffmpeg writes to a .part name — which
    # @claude the .mp4-globbing listing, counter, and recount never match — and
    # @claude the clip appears under its final name only once complete. -f mp4
    # @claude is explicit because the .part extension no longer implies it.
    part_path = dest_dir / f"{base}.mp4.part"
    meta_path = dest_dir / f"{base}.json"
    manifest_path = Path(SEGMENT_DIR) / f"{base}.segments.txt"
    write_concat_manifest(selected_segments, manifest_path)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "concat", "-safe", "0", "-i", str(manifest_path),
        "-c", "copy", "-f", "mp4", str(part_path),
    ]
    ffmpeg_started_at = time.time()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=int(TRIGGER_PRE_EVENT_SEC + TRIGGER_POST_EVENT_SEC + 15),
            check=False,
        )
        ffmpeg_elapsed_ms = int(round((time.time() - ffmpeg_started_at) * 1000))
        if result.returncode != 0:
            cleanup_partial_outputs(part_path, meta_path)
            log.error(
                "trigger-clip finalize failed: %s (exit=%d, stderr=%r)",
                out_path.name, result.returncode, summarize_ffmpeg_stderr(result.stderr),
            )
            status.set_clip_storage("error", "ffmpeg_failed",
                                    bytes_to_mb(shutil.disk_usage(dest_dir).free))
            return None
    except subprocess.TimeoutExpired:
        cleanup_partial_outputs(part_path, meta_path)
        status.set_clip_storage("error", "ffmpeg_timeout",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None
    except Exception as e:
        log.error("trigger-clip finalize error: %s", e)
        cleanup_partial_outputs(part_path, meta_path)
        status.set_clip_storage("error", "ffmpeg_error",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None
    finally:
        try:
            manifest_path.unlink()
        except OSError:
            pass

    if not part_path.exists():
        status.set_clip_storage("error", "ffmpeg_failed",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None
    os.replace(part_path, out_path)
    clip_size_bytes = out_path.stat().st_size
    clip_duration_s = probe_clip_duration_seconds(out_path)
    log.info(
        "trigger-clip finalize done: %s (segments=%d, size=%d, duration=%s)",
        out_path.name, len(selected_segments), clip_size_bytes,
        clip_duration_s if clip_duration_s is not None else "unknown",
    )

    _write_sidecar(
        meta_path,
        build_trigger_clip_meta(
            event_time=event_time,
            matched_keywords=matched_keywords,
            vlm_text=vlm_text,
            record_requested_at=record_requested_at,
            ffmpeg_started_at=ffmpeg_started_at,
            ffmpeg_elapsed_ms=ffmpeg_elapsed_ms,
            clip_size_bytes=clip_size_bytes,
            clip_duration_s=clip_duration_s,
            last_frame_time=last_frame_time,
            inference_started_at=inference_started_at,
            inference_elapsed_ms=inference_elapsed_ms,
        ) | {
            "record_mode": "segment_rollover",
            "segment_window_start_ms": int(round(window_start * 1000)),
            "segment_window_end_ms": int(round(window_end * 1000)),
            "selected_segment_count": len(selected_segments),
            "capture_source": "streamer_rollover_segments",
            "video_codec_mode": "copy_concat",
        },
    )
    # @claude Counted only after the sidecar exists: the count change is the
    # @claude client's list-refresh signal, and the listing hides clips without
    # @claude metadata — a count that moves first announces a clip the refresh
    # @claude cannot see (SDD §6.4 (4)).
    count_added_clip(clip_size_bytes)
    status.set_clip_storage(
        "ok",
        capacity.reason if capacity.reason != "ok" else "",
        bytes_to_mb(shutil.disk_usage(dest_dir).free),
    )
    return out_path.name


def _record_direct_clip(
    matched_keywords: list[str],
    vlm_text: str,
    event_time: float,
    *,
    last_frame_time: float | None = None,
    inference_started_at: float | None = None,
    inference_elapsed_ms: int | None = None,
) -> str | None:
    """Record forward from the event moment directly off RTSP (no pre-event)."""
    record_requested_at = time.time()
    base, dest_dir = _event_base_name(event_time)

    capacity = _prune_with_history(CLIP_DIR, CLIP_STORAGE_POLICY)
    if not capacity.ok:
        status.set_clip_storage("skipped", capacity.reason, bytes_to_mb(capacity.free_bytes))
        return None

    out_path = dest_dir / f"{base}.mp4"
    # @claude Same atomic-publish pattern as the rollover path (SDD §5.4).
    part_path = dest_dir / f"{base}.mp4.part"
    meta_path = dest_dir / f"{base}.json"
    cmd = [
        "ffmpeg", "-y",
        "-rtsp_transport", "tcp",
        "-i", MEDIAMTX_URL,
        "-t", str(TRIGGER_CLIP_DUR),
        "-c:v", "copy", "-an",
        "-f", "mp4", str(part_path),
    ]
    ffmpeg_started_at = time.time()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=TRIGGER_CLIP_DUR + 10,
            check=False,
        )
        ffmpeg_elapsed_ms = int(round((time.time() - ffmpeg_started_at) * 1000))
        if result.returncode != 0:
            cleanup_partial_outputs(part_path, meta_path)
            log.error(
                "direct trigger-clip failed: %s (exit=%d, stderr=%r)",
                out_path.name, result.returncode, summarize_ffmpeg_stderr(result.stderr),
            )
            status.set_clip_storage("error", "ffmpeg_failed",
                                    bytes_to_mb(shutil.disk_usage(dest_dir).free))
            return None
    except subprocess.TimeoutExpired:
        cleanup_partial_outputs(part_path, meta_path)
        status.set_clip_storage("error", "ffmpeg_timeout",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None
    except Exception as e:
        log.error("direct trigger-clip error: %s", e)
        cleanup_partial_outputs(part_path, meta_path)
        status.set_clip_storage("error", "ffmpeg_error",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None

    if not part_path.exists():
        status.set_clip_storage("error", "ffmpeg_failed",
                                bytes_to_mb(shutil.disk_usage(dest_dir).free))
        return None
    os.replace(part_path, out_path)
    clip_size_bytes = out_path.stat().st_size
    _write_sidecar(
        meta_path,
        build_trigger_clip_meta(
            event_time=event_time,
            matched_keywords=matched_keywords,
            vlm_text=vlm_text,
            record_requested_at=record_requested_at,
            ffmpeg_started_at=ffmpeg_started_at,
            ffmpeg_elapsed_ms=ffmpeg_elapsed_ms,
            clip_size_bytes=clip_size_bytes,
            clip_duration_s=probe_clip_duration_seconds(out_path),
            last_frame_time=last_frame_time,
            inference_started_at=inference_started_at,
            inference_elapsed_ms=inference_elapsed_ms,
        ),
    )
    # @claude Same ordering rule as the rollover path: sidecar first, count last.
    count_added_clip(clip_size_bytes)
    status.set_clip_storage("ok", "", bytes_to_mb(shutil.disk_usage(dest_dir).free))
    return out_path.name


def _write_sidecar(meta_path: Path, meta: dict) -> None:
    # @claude Temp file + os.replace: the listing treats the sidecar as the
    # @claude clip's validity marker, so a torn sidecar must never exist
    # @claude (SDD §5.4).
    try:
        tmp = Path(f"{meta_path}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, meta_path)
    except Exception as e:
        log.error("metadata save error: %s", e)

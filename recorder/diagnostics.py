"""Helpers for trigger-clip observability and postmortem metadata."""

from __future__ import annotations

import subprocess
from pathlib import Path


def summarize_ffmpeg_stderr(
    stderr: bytes | str | None,
    *,
    max_lines: int = 8,
    max_chars: int = 1200,
) -> str:
    """Return a compact trailing summary of ffmpeg stderr."""
    if stderr is None:
        return ""
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", errors="replace")
    else:
        text = stderr
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    summary = "\n".join(lines[-max_lines:])
    if len(summary) > max_chars:
        summary = summary[-max_chars:]
    return summary


def probe_clip_duration_seconds(path: str | Path) -> float | None:
    """Best-effort mp4 duration probe via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    try:
        return round(float(raw), 3)
    except ValueError:
        return None


def build_trigger_clip_meta(
    *,
    event_time: float,
    matched_keywords: list[str],
    vlm_text: str,
    record_requested_at: float,
    ffmpeg_started_at: float,
    ffmpeg_elapsed_ms: int,
    clip_size_bytes: int,
    clip_duration_s: float | None,
    last_frame_time: float | None = None,
    inference_started_at: float | None = None,
    inference_elapsed_ms: int | None = None,
) -> dict:
    """Build clip sidecar metadata with diagnostic timing fields."""
    meta = {
        "timestamp": int(event_time),
        "event_time_ms": int(round(event_time * 1000)),
        "keywords": matched_keywords,
        "vlm_text": vlm_text,
        "record_requested_at_ms": int(round(record_requested_at * 1000)),
        "ffmpeg_started_at_ms": int(round(ffmpeg_started_at * 1000)),
        "start_delay_ms": int(round((ffmpeg_started_at - event_time) * 1000)),
        "ffmpeg_elapsed_ms": ffmpeg_elapsed_ms,
        "clip_size_bytes": clip_size_bytes,
        "clip_duration_s": clip_duration_s,
        "capture_source": "mediamtx_rtsp",
        "video_codec_mode": "copy",
    }
    if last_frame_time is not None:
        meta["frame_time_ms"] = int(round(last_frame_time * 1000))
        meta["frame_to_event_ms"] = int(round((event_time - last_frame_time) * 1000))
    if inference_started_at is not None:
        meta["inference_started_at_ms"] = int(round(inference_started_at * 1000))
    if inference_elapsed_ms is not None:
        meta["inference_elapsed_ms"] = int(inference_elapsed_ms)
    return meta

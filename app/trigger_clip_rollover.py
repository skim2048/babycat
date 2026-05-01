"""Rolling-segment helpers for trigger clip assembly."""

from __future__ import annotations

import os
import time
from pathlib import Path


SEGMENT_SUFFIX = ".ts"
SEGMENT_TIME_FORMAT = "%Y%m%d_%H%M%S"


def ensure_segment_dir(path: str | Path) -> Path:
    segment_dir = Path(path)
    segment_dir.mkdir(parents=True, exist_ok=True)
    return segment_dir


def segment_path_for_time(base_dir: str | Path, started_at: float) -> Path:
    stamp = time.strftime(SEGMENT_TIME_FORMAT, time.localtime(started_at))
    return Path(base_dir) / f"{stamp}{SEGMENT_SUFFIX}"


def parse_segment_start(path: str | Path) -> float | None:
    name = Path(path).name
    if not name.endswith(SEGMENT_SUFFIX):
        return None
    stem = name[: -len(SEGMENT_SUFFIX)]
    try:
        parsed = time.strptime(stem, SEGMENT_TIME_FORMAT)
    except ValueError:
        return None
    return float(time.mktime(parsed))


def list_segments(base_dir: str | Path) -> list[Path]:
    segment_dir = Path(base_dir)
    if not segment_dir.exists():
        return []
    segments = [path for path in segment_dir.glob(f"*{SEGMENT_SUFFIX}") if path.is_file()]
    segments.sort()
    return segments


def latest_segment_age_seconds(base_dir: str | Path, *, now: float | None = None) -> float | None:
    segments = list_segments(base_dir)
    if not segments:
        return None
    started_at = parse_segment_start(segments[-1])
    if started_at is None:
        return None
    current = time.time() if now is None else now
    return max(0.0, current - started_at)


def select_segments_for_window(
    base_dir: str | Path,
    window_start: float,
    window_end: float,
    *,
    segment_span_s: float,
) -> list[Path]:
    selected: list[Path] = []
    for path in list_segments(base_dir):
        started_at = parse_segment_start(path)
        if started_at is None:
            continue
        ended_at = started_at + max(0.001, segment_span_s)
        if ended_at <= window_start:
            continue
        if started_at >= window_end:
            continue
        selected.append(path)
    return selected


def purge_old_segments(base_dir: str | Path, *, retain_since: float) -> int:
    removed = 0
    for path in list_segments(base_dir):
        started_at = parse_segment_start(path)
        if started_at is None:
            continue
        if started_at >= retain_since:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def write_concat_manifest(segment_paths: list[Path], manifest_path: str | Path) -> Path:
    manifest = Path(manifest_path)
    lines = []
    for path in segment_paths:
        escaped = str(path).replace("'", "'\\''")
        lines.append(f"file '{escaped}'\n")
    manifest.write_text("".join(lines), encoding="utf-8")
    return manifest


def segment_recorder_cmd(
    source_url: str,
    segment_dir: str | Path,
    *,
    segment_time_s: int,
) -> list[str]:
    pattern = str(Path(segment_dir) / f"%Y%m%d_%H%M%S{SEGMENT_SUFFIX}")
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-rtsp_transport",
        "tcp",
        "-i",
        source_url,
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(segment_time_s),
        "-segment_format",
        "mpegts",
        "-reset_timestamps",
        "1",
        "-strftime",
        "1",
        pattern,
    ]


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

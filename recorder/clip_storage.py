"""Helpers for clip-storage capacity checks, old-clip pruning, and the
in-memory clip counter."""

import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# @claude Files below 10 KB cannot hold a playable clip and are treated as
# @claude damaged; the clip listing and the counter exclude them by the same
# @claude rule (SDD §5.3).
MIN_CLIP_SIZE = 10240

# @claude In-memory clip counter: /status serves this instead of walking the
# @claude clip tree on every monitoring poll (2s). Recomputed once at startup;
# @claude every mutation site — finalize, direct record, user deletion,
# @claude capacity pruning — adjusts it. The count doubles as the clip-list
# @claude invalidation signal for the client, so it must move immediately.
_count_lock = threading.Lock()
_clip_count = 0


def recount_clips(base: str | Path) -> int:
    global _clip_count
    count = sum(1 for p in list_clip_files(base) if p.stat().st_size >= MIN_CLIP_SIZE)
    with _count_lock:
        _clip_count = count
    return count


def clip_count() -> int:
    with _count_lock:
        return _clip_count


def count_added_clip(size_bytes: int) -> None:
    global _clip_count
    if size_bytes < MIN_CLIP_SIZE:
        return
    with _count_lock:
        _clip_count += 1


def count_removed_clip(size_bytes: int) -> None:
    global _clip_count
    if size_bytes < MIN_CLIP_SIZE:
        return
    with _count_lock:
        _clip_count = max(0, _clip_count - 1)


@dataclass(frozen=True)
class ClipStoragePolicy:
    min_free_bytes: int
    target_free_bytes: int


@dataclass(frozen=True)
class ClipStorageResult:
    ok: bool
    reason: str
    free_bytes: int
    deleted_files: int = 0
    deleted_bytes: int = 0


def bytes_to_mb(value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, value // (1024 * 1024))


def usage_path(path: str | Path) -> Path:
    current = Path(path)
    while not current.exists():
        if current.parent == current:
            return current
        current = current.parent
    return current


def free_bytes(path: str | Path) -> int:
    return shutil.disk_usage(usage_path(path)).free


def list_clip_files(base: str | Path) -> list[Path]:
    root = Path(base)
    if not root.exists():
        return []
    clips = [path for path in root.rglob("*.mp4") if path.is_file()]
    clips.sort(key=lambda path: path.stat().st_mtime)
    return clips


def delete_clip_pair(mp4_path: str | Path) -> int:
    path = Path(mp4_path)
    deleted_bytes = 0

    if path.exists():
        mp4_size = path.stat().st_size
        deleted_bytes += mp4_size
        path.unlink()
        count_removed_clip(mp4_size)

    meta_path = path.with_suffix(".json")
    if meta_path.exists():
        deleted_bytes += meta_path.stat().st_size
        meta_path.unlink()

    return deleted_bytes


def ensure_clip_capacity(base: str | Path, policy: ClipStoragePolicy) -> ClipStorageResult:
    root = Path(base)
    current_free = free_bytes(root)

    if current_free >= policy.min_free_bytes:
        return ClipStorageResult(ok=True, reason="ok", free_bytes=current_free)

    deleted_files = 0
    deleted_bytes = 0
    target_free = max(policy.min_free_bytes, policy.target_free_bytes)

    # @claude Oldest first, until the target is reached or no clip is left
    # @claude (FR-033): the loop is bounded by the clip count.
    for clip_path in list_clip_files(root):
        deleted_bytes += delete_clip_pair(clip_path)
        deleted_files += 1
        current_free = free_bytes(root)
        if current_free >= target_free:
            break

    if current_free >= policy.min_free_bytes:
        return ClipStorageResult(
            ok=True,
            reason="pruned_old_clips" if deleted_files else "ok",
            free_bytes=current_free,
            deleted_files=deleted_files,
            deleted_bytes=deleted_bytes,
        )

    return ClipStorageResult(
        ok=False,
        reason="low_disk_space",
        free_bytes=current_free,
        deleted_files=deleted_files,
        deleted_bytes=deleted_bytes,
    )


def cleanup_partial_outputs(*paths: str | Path) -> None:
    for raw_path in paths:
        path = Path(raw_path)
        try:
            if path.exists():
                path.unlink()
        except OSError as e:
            log.warning("partial output %s not removed: %s", path, e)

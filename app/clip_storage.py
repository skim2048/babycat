"""Helpers for clip-storage capacity checks and old-clip pruning."""

from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass(frozen=True)
class ClipStoragePolicy:
    min_free_bytes: int
    target_free_bytes: int
    prune_max_files: int


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
        deleted_bytes += path.stat().st_size
        path.unlink()

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

    for clip_path in list_clip_files(root):
        if deleted_files >= policy.prune_max_files:
            break
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
        except OSError:
            pass

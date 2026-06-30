"""Scan the videos/ directory and produce a serialized tree of mp4 files."""

from __future__ import annotations

import os
from pathlib import Path

from .schemas import DirectoryNode, FileNode


MP4_SUFFIX = ".mp4"


def scan(videos_dir: str | os.PathLike) -> DirectoryNode:
    """
    Walk `videos_dir` and return a DirectoryNode tree.

    Directories are listed before files; both are sorted by name. Files
    other than mp4 are ignored. Empty directories (after filtering) are
    preserved so the UI can show the user that the folder exists.
    """
    root = Path(videos_dir)
    return _build(root, root, root.name or "videos")


def _build(path: Path, base: Path, label: str) -> DirectoryNode:
    children: list[DirectoryNode | FileNode] = []
    if path.is_dir():
        try:
            entries = list(path.iterdir())
        except OSError:
            entries = []
        dirs = sorted([e for e in entries if e.is_dir()], key=lambda p: p.name.lower())
        files = sorted(
            [e for e in entries if e.is_file() and e.suffix.lower() == MP4_SUFFIX],
            key=lambda p: p.name.lower(),
        )
        for d in dirs:
            children.append(_build(d, base, d.name))
        for f in files:
            children.append(_file_node(f, base))
    return DirectoryNode(name=label, children=children)


def _file_node(path: Path, base: Path) -> FileNode:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    rel = path.relative_to(base).as_posix()
    return FileNode(name=path.name, path=rel, size_bytes=size)


def resolve(videos_dir: str | os.PathLike, rel_path: str) -> Path | None:
    """
    Resolve a tree-relative path to an absolute Path under `videos_dir`.

    Returns None if the resolved path escapes the base, is not a file, or
    is not an mp4. This is the boundary that protects against directory
    traversal from the API surface.
    """
    base = Path(videos_dir).resolve()
    candidate = (base / rel_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() != MP4_SUFFIX:
        return None
    return candidate

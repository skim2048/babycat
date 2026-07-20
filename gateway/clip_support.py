"""Clip path helpers shared by the API clip endpoints."""

import re
from pathlib import Path


def parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    match = re.match(r"bytes=(\d+)-(\d*)", range_header or "")
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return None
    return start, end


def resolve_clip_path(base: Path, name: str) -> Path | None:
    if "/" in name or "\\" in name or ".." in name:
        return None
    if len(name) >= 8 and name[:8].isdigit():
        candidate = base / name[:4] / name[4:6] / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for path in base.rglob(name):
        if path.is_file():
            return path
    return None

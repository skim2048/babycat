import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import clip_support  # noqa: E402


def test_resolve_clip_path_prefers_inferred_year_month_path(tmp_path: Path):
    base = tmp_path / "clips"
    target = base / "2026" / "04"
    target.mkdir(parents=True)
    file_path = target / "20260423_120000_001.mp4"
    file_path.write_bytes(b"data")

    resolved = clip_support.resolve_clip_path(base, file_path.name)

    assert resolved == file_path


def test_resolve_clip_path_rejects_path_traversal():
    resolved = clip_support.resolve_clip_path(Path("/tmp/clips"), "../secret.mp4")
    assert resolved is None


def test_parse_byte_range_accepts_open_end_range():
    assert clip_support.parse_byte_range("bytes=10-", 100) == (10, 99)


def test_parse_byte_range_rejects_invalid_range():
    assert clip_support.parse_byte_range("bytes=120-130", 100) is None

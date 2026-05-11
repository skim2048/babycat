import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import hardware  # noqa: E402


def test_disk_usage_uses_nearest_existing_parent(tmp_path: Path):
    missing_clip_path = tmp_path / "2026" / "05"

    usage = hardware.disk_usage(str(missing_clip_path))

    assert usage["disk_total_mb"] > 0
    assert usage["disk_free_mb"] > 0
    assert usage["disk_path"] == str(tmp_path)


def test_disk_usage_returns_empty_values_when_unset():
    usage = hardware.disk_usage("")

    assert usage == {
        "disk_used_mb": 0,
        "disk_total_mb": 0,
        "disk_free_mb": 0,
        "disk_path": "",
    }


def test_disk_usage_returns_empty_values_when_read_fails(monkeypatch, tmp_path: Path):
    def raise_os_error(path):
        raise OSError("disk unavailable")

    monkeypatch.setattr(hardware.shutil, "disk_usage", raise_os_error)

    usage = hardware.disk_usage(str(tmp_path))

    assert usage["disk_used_mb"] == 0
    assert usage["disk_total_mb"] == 0
    assert usage["disk_free_mb"] == 0
    assert usage["disk_path"] == str(tmp_path)

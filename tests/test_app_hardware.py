import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import hardware  # noqa: E402


class _FakeSysfsFile:
    def __init__(self, value=None, error=None):
        self._value = value
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        if self._error is not None:
            raise self._error
        return self._value


def test_read_sysfs_returns_none_when_read_returns_none(monkeypatch):
    monkeypatch.setattr(hardware, "open", lambda *args, **kwargs: _FakeSysfsFile(None), raising=False)

    assert hardware._read_sysfs("/sys/fake") is None


def test_read_sysfs_returns_none_when_text_wrapper_type_error_occurs(monkeypatch):
    error = TypeError("can't concat NoneType to bytes")
    monkeypatch.setattr(hardware, "open", lambda *args, **kwargs: _FakeSysfsFile(error=error), raising=False)

    assert hardware._read_sysfs("/sys/fake") is None


def test_hardware_snapshot_preserves_unavailable_sysfs_as_none(monkeypatch):
    monkeypatch.setattr(hardware, "_read_sysfs", lambda path: None)

    snap = hardware.HardwareMonitor().snapshot()

    assert snap["gpu_load"] is None
    assert snap["cpu_temp"] is None
    assert snap["gpu_temp"] is None


def test_hardware_snapshot_handles_non_numeric_sysfs_values(monkeypatch):
    monkeypatch.setattr(hardware, "_read_sysfs", lambda path: "not-ready")

    snap = hardware.HardwareMonitor().snapshot()

    assert snap["gpu_load"] is None
    assert snap["cpu_temp"] is None
    assert snap["gpu_temp"] is None


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

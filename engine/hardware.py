"""
Jetson Orin NX hardware monitor.

Reads CPU/RAM/GPU utilization and temperatures from /proc and /sys.

@claude
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

GPU_LOAD_PATH    = "/sys/devices/platform/bus@0/17000000.gpu/load"
CPU_THERMAL_PATH = "/sys/devices/virtual/thermal/thermal_zone0/temp"
GPU_THERMAL_PATH = "/sys/devices/virtual/thermal/thermal_zone1/temp"
MB = 1024 * 1024


def _read_sysfs(path: str) -> Optional[str]:
    """Read a small sysfs node without letting transient EAGAIN break callers."""
    try:
        with open(path, "rb", buffering=0) as f:
            raw = f.read(4096)
        if not raw:
            return None
        return raw.decode("utf-8").strip() or None
    except Exception as e:
        log.debug("sysfs read failed for %s: %s", path, e)
        return None


def _scaled_sysfs_float(path: str, divisor: float) -> float | None:
    value = _read_sysfs(path)
    if value is None:
        return None
    try:
        return int(value) / divisor
    except (TypeError, ValueError) as e:
        log.debug("sysfs parse failed for %s: %s", path, e)
        return None


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _nearest_existing_path(path: Path) -> Path | None:
    current_path = path
    while not current_path.exists():
        parent_path = current_path.parent
        if parent_path == current_path:
            return None
        current_path = parent_path
    return current_path


def disk_usage(path: str) -> dict:
    """Return usage for the filesystem backing path, in MB."""
    empty = {
        "disk_used_mb": 0,
        "disk_total_mb": 0,
        "disk_free_mb": 0,
        "disk_path": path or "",
    }
    if not path:
        return empty

    existing_path = _nearest_existing_path(Path(path))
    if existing_path is None:
        return empty

    try:
        usage = shutil.disk_usage(existing_path)
    except Exception as e:
        log.debug("Disk usage read failed for %s: %s", existing_path, e)
        return empty

    return {
        "disk_used_mb": usage.used // MB,
        "disk_total_mb": usage.total // MB,
        "disk_free_mb": usage.free // MB,
        "disk_path": str(existing_path),
    }


class HardwareMonitor:

    def __init__(self):
        self._prev_cpu: Optional[tuple[int, int]] = None
        self._cpu_percent: float = 0.0

    def cpu_percent(self) -> float:
        try:
            with open("/proc/stat") as f:
                line = f.readline()
            parts  = line.split()
            values = [int(x) for x in parts[1:9]]
            total  = sum(values)
            idle   = values[3] + values[4]
            if self._prev_cpu is not None:
                d_total = total - self._prev_cpu[0]
                d_idle  = idle  - self._prev_cpu[1]
                if d_total > 0:
                    self._cpu_percent = (1 - d_idle / d_total) * 100
            self._prev_cpu = (total, idle)
            return self._cpu_percent
        except Exception as e:
            log.debug("CPU percent read failed: %s", e)
            return 0.0

    def ram_usage(self) -> tuple[int, int]:
        """Return (used_mb, total_mb). @claude"""
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if parts[0] in ("MemTotal:", "MemAvailable:"):
                        info[parts[0]] = int(parts[1])
            total = info.get("MemTotal:", 0)
            avail = info.get("MemAvailable:", 0)
            return ((total - avail) // 1024, total // 1024)
        except Exception as e:
            log.debug("RAM usage read failed: %s", e)
            return (0, 0)

    def gpu_load(self) -> float | None:
        return _scaled_sysfs_float(GPU_LOAD_PATH, 10.0)

    def cpu_temp(self) -> float | None:
        return _scaled_sysfs_float(CPU_THERMAL_PATH, 1000.0)

    def gpu_temp(self) -> float | None:
        return _scaled_sysfs_float(GPU_THERMAL_PATH, 1000.0)

    def snapshot(self) -> dict:
        ram_used, ram_total = self.ram_usage()
        return {
            "cpu_percent": round(self.cpu_percent(), 1),
            "ram_used_mb": ram_used,
            "ram_total_mb": ram_total,
            "gpu_load":    _round_or_none(self.gpu_load()),
            "cpu_temp":    _round_or_none(self.cpu_temp()),
            "gpu_temp":    _round_or_none(self.gpu_temp()),
        }

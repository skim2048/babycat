"""
Jetson Orin NX 하드웨어 모니터

/proc, /sys에서 CPU·RAM·GPU 사용률과 온도를 읽는다.
"""

from typing import Optional


GPU_LOAD_PATH    = "/sys/devices/platform/bus@0/17000000.gpu/load"
CPU_THERMAL_PATH = "/sys/devices/virtual/thermal/thermal_zone0/temp"
GPU_THERMAL_PATH = "/sys/devices/virtual/thermal/thermal_zone1/temp"


def _read_sysfs(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except (OSError, IOError):
        return None


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
        except Exception:
            return 0.0

    def ram_usage(self) -> tuple[int, int]:
        """(used_mb, total_mb)"""
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
        except Exception:
            return (0, 0)

    def gpu_load(self) -> float:
        val = _read_sysfs(GPU_LOAD_PATH)
        return int(val) / 10.0 if val else 0.0

    def cpu_temp(self) -> float:
        val = _read_sysfs(CPU_THERMAL_PATH)
        return int(val) / 1000.0 if val else 0.0

    def gpu_temp(self) -> float:
        val = _read_sysfs(GPU_THERMAL_PATH)
        return int(val) / 1000.0 if val else 0.0

    def snapshot(self) -> dict:
        ram_used, ram_total = self.ram_usage()
        return {
            "cpu_percent": round(self.cpu_percent(), 1),
            "ram_used_mb": ram_used,
            "ram_total_mb": ram_total,
            "gpu_load":    round(self.gpu_load(), 1),
            "cpu_temp":    round(self.cpu_temp(), 1),
            "gpu_temp":    round(self.gpu_temp(), 1),
        }

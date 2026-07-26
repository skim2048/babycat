"""Recorder-owned runtime status, exposed to the router's monitoring merge."""

import threading
import time


class RecorderStatus:
    """Thread-safe status holder (clip storage, segment recorder, buffer)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        self.buffer_active: bool = False
        self.clip_storage_state: str = "ok"
        self.clip_storage_reason: str = ""
        self.clip_storage_free_mb: int | None = None
        self.segment_recorder_state: str = "disabled"
        self.segment_recorder_error: str = ""
        self.segment_recorder_segment_count: int = 0
        self.segment_recorder_last_segment_age_s: float | None = None

    def set_buffer_active(self, active: bool) -> None:
        with self._lock:
            self.buffer_active = active

    def set_clip_storage(self, state: str, reason: str = "", free_mb: int | None = None) -> None:
        with self._lock:
            self.clip_storage_state = state
            self.clip_storage_reason = reason
            self.clip_storage_free_mb = free_mb

    def set_segment_recorder(
        self,
        state: str,
        *,
        error: str = "",
        segment_count: int | None = None,
        last_segment_age_s: float | None = None,
    ) -> None:
        with self._lock:
            self.segment_recorder_state = state
            self.segment_recorder_error = error
            if segment_count is not None:
                self.segment_recorder_segment_count = segment_count
            self.segment_recorder_last_segment_age_s = last_segment_age_s

    def _uptime_text(self) -> str:
        uptime_s = int(time.time() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m:02d}m {s:02d}s"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "buffer_active": self.buffer_active,
                "clip_storage_state": self.clip_storage_state,
                "clip_storage_reason": self.clip_storage_reason,
                "clip_storage_free_mb": self.clip_storage_free_mb,
                "segment_recorder_state": self.segment_recorder_state,
                "segment_recorder_error": self.segment_recorder_error,
                "segment_recorder_segment_count": self.segment_recorder_segment_count,
                "segment_recorder_last_segment_age_s": self.segment_recorder_last_segment_age_s,
                "uptime": self._uptime_text(),
            }


status = RecorderStatus()

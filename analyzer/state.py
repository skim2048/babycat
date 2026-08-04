"""
Analyzer-owned shared runtime state.

Holds only what the analyzer owns (SDD §6.4 (4)): inference results,
pipeline state, VLM lifecycle, prompt and trigger keywords. Hardware,
storage, and PTZ state live with their owning components and are merged
by the router.

@claude
"""

import io
import queue
import threading
import time
from typing import Optional

from PIL import Image


class AppState:
    """Shared state between the pipeline and the HTTP server. @claude"""

    def __init__(self):
        self._lock = threading.Lock()
        self._sse_lock = threading.Lock()
        self._start_time = time.time()

        self.frame:       Optional[Image.Image] = None
        self.frame_w:     int   = 0
        self.frame_h:     int   = 0
        self.infer_label: str   = ""
        self.infer_raw:   str   = ""
        self.infer_ms:    float = 0.0

        self._ring      = None
        self._ring_size: int  = 0
        self._config:   dict  = {}

        self._sse_queues: list[queue.Queue] = []
        self.inference_prompt: str = ""
        self.trigger_keywords: list[str] = []
        self.event_triggered: bool = False
        self.analysis_active: bool = False
        self.pipeline_state: str = "idle"
        self.pipeline_state_detail: str = "waiting_for_vlm"
        self.pipeline_started_at: float = 0.0
        self.pipeline_last_frame_at: float = 0.0
        self.pipeline_restart_count: int = 0

        # @claude VLM load lifecycle — initializing | downloading | compiling | loading | ready | switching | error.
        self.vlm_state: str = "initializing"
        self.vlm_error: str = ""
        self.vlm_models: list[str] = []
        self.vlm_current_model: str = ""

    def set_vlm_state(self, state: str, error: str = ""):
        with self._lock:
            self.vlm_state = state
            self.vlm_error = error
            self._normalize_pipeline_state_detail_locked()
        self._sse_push()

    def set_vlm_models(self, models: list[str], current: str):
        with self._lock:
            self.vlm_models = list(models)
            self.vlm_current_model = current
        self._sse_push()

    def set_vlm_current_model(self, current: str):
        with self._lock:
            self.vlm_current_model = current
        self._sse_push()

    def _sse_push(self):
        with self._sse_lock:
            for q in self._sse_queues:
                try:
                    q.put_nowait(1)
                except queue.Full:
                    pass

    def set_refs(self, ring, ring_size: int, config: dict):
        self._ring      = ring
        self._ring_size = ring_size
        self._config    = config

    def set_prompt(self, prompt: str):
        with self._lock:
            self.inference_prompt = prompt

    def get_prompt(self) -> str:
        with self._lock:
            return self.inference_prompt

    def set_triggers(self, keywords: list[str]):
        with self._lock:
            self.trigger_keywords = keywords

    def get_triggers(self) -> list[str]:
        with self._lock:
            return list(self.trigger_keywords)

    def set_analysis_active(self, active: bool):
        with self._lock:
            self.analysis_active = active
            if not active:
                # @claude Stop clears the last judgment: without this the final
                # @claude event stays in every later SSE snapshot and the UI
                # @claude keeps showing it (bulb, overlay) after analysis ends.
                self.infer_label = ""
                self.infer_raw = ""
                self.event_triggered = False
        self._sse_push()

    def is_analysis_active(self) -> bool:
        with self._lock:
            return self.analysis_active

    def update_frame(self, frame: Image.Image, orig_w: int, orig_h: int):
        transitioned = False
        with self._lock:
            # @claude A frame straggling in from a torn-down pipeline must not
            # @claude flip the state back to streaming after a stop (SDD §7.3).
            if not self.analysis_active:
                return
            self.frame   = frame.copy()
            self.frame_w = orig_w
            self.frame_h = orig_h
            now = time.time()
            self.pipeline_last_frame_at = now
            if self.pipeline_started_at == 0.0:
                self.pipeline_started_at = now
            transitioned = self.pipeline_state != "streaming"
            self.pipeline_state = "streaming"
            self.pipeline_state_detail = ""
        if transitioned:
            self._sse_push()

    def update_inference(self, label: str, raw: str, elapsed_ms: float,
                         event_triggered: bool = False):
        with self._lock:
            self.infer_label = label
            self.infer_raw   = raw
            self.infer_ms    = elapsed_ms
            self.event_triggered = event_triggered
        self._sse_push()

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            if self.frame is None:
                return None
            buf = io.BytesIO()
            self.frame.save(buf, format="JPEG", quality=80)
            return buf.getvalue()

    def _inference_snapshot_locked(self) -> dict:
        return {
            "frame_w":     self.frame_w,
            "frame_h":     self.frame_h,
            "infer_label": self.infer_label,
            "infer_raw":   self.infer_raw,
            "infer_ms":    round(self.infer_ms, 1),
        }

    def _runtime_snapshot_locked(self) -> dict:
        return {
            "ring_len":      len(self._ring) if self._ring is not None else 0,
            "ring_size":     self._ring_size,
            "inference_prompt": self.inference_prompt,
            "trigger_keywords": ",".join(self.trigger_keywords),
            "event_triggered": self.event_triggered,
            "analysis_active": self.analysis_active,
            "vlm_state": self.vlm_state,
            "vlm_error": self.vlm_error,
            "vlm_models": list(self.vlm_models),
            "vlm_current_model": self.vlm_current_model,
            **{f"cfg_{k}": v for k, v in self._config.items()},
        }

    def _stream_snapshot_locked(self) -> dict:
        now = time.time()
        active_for = None
        if self.pipeline_started_at > 0.0:
            active_for = round(max(0.0, now - self.pipeline_started_at), 1)

        last_frame_age = None
        if self.pipeline_last_frame_at > 0.0:
            last_frame_age = round(max(0.0, now - self.pipeline_last_frame_at), 1)

        return {
            "pipeline_state": self.pipeline_state,
            "pipeline_state_detail": self._current_pipeline_state_detail_locked(),
            "pipeline_source_protocol": "rtsp",
            "pipeline_source_transport": "tcp",
            "pipeline_active_for_s": active_for,
            "pipeline_last_frame_age_s": last_frame_age,
            "pipeline_restart_count": self.pipeline_restart_count,
        }

    def mark_pipeline_starting(self, reason: str, restart: bool = False, started_at: float | None = None):
        with self._lock:
            self.pipeline_state = "restarting" if restart else "starting"
            self.pipeline_state_detail = reason
            self.pipeline_started_at = started_at or time.time()
            self.pipeline_last_frame_at = 0.0
            if restart:
                self.pipeline_restart_count += 1
        self._sse_push()

    def mark_pipeline_idle(self, reason: str):
        with self._lock:
            self.pipeline_state = "idle"
            self.pipeline_state_detail = reason
            self.pipeline_started_at = 0.0
            self.pipeline_last_frame_at = 0.0
        self._sse_push()

    def mark_pipeline_stalled(self, reason: str):
        with self._lock:
            self.pipeline_state = "stalled"
            self.pipeline_state_detail = reason
        self._sse_push()

    def mark_pipeline_stopped(self, reason: str):
        with self._lock:
            self.pipeline_state = "stopped"
            self.pipeline_state_detail = reason
            self.pipeline_started_at = 0.0
        self._sse_push()

    def _current_pipeline_state_detail_locked(self) -> str:
        detail = self.pipeline_state_detail
        if detail == "waiting_for_vlm" and self.vlm_state == "ready":
            return ""
        return detail

    def _normalize_pipeline_state_detail_locked(self) -> None:
        self.pipeline_state_detail = self._current_pipeline_state_detail_locked()

    def _uptime_text(self) -> str:
        uptime_s = int(time.time() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m:02d}m {s:02d}s"

    def snapshot(self) -> dict:
        # @claude No "uptime" here: the recorder's /status carries it (always-on
        # @claude component), and the router merge must not see two of them.
        with self._lock:
            return {
                **self._inference_snapshot_locked(),
                **self._stream_snapshot_locked(),
                **self._runtime_snapshot_locked(),
            }

    def sse_subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._sse_lock:
            self._sse_queues.append(q)
        return q

    def sse_unsubscribe(self, q: queue.Queue):
        with self._sse_lock:
            try:
                self._sse_queues.remove(q)
            except ValueError:
                pass


state = AppState()

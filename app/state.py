"""
Shared application state.

Aggregates pipeline state (GStreamer callback / inference worker), VLM
lifecycle, prompt / trigger keywords, and clip cache behind a single
object that the HTTP server reads from.

@claude
"""

import io
import json
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from hardware import HardwareMonitor
import ptz


class AppState:
    """Shared state between the pipeline and the HTTP server. @claude"""

    def __init__(self):
        self._lock = threading.Lock()
        self._sse_lock = threading.Lock()
        self._hw   = HardwareMonitor()
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
        self._clip_dir: str = ""
        self._clip_cache: list[dict] = []
        self._clip_cache_time: float = 0.0
        self.pipeline_state: str = "idle"
        self.pipeline_status_reason: str = "waiting_for_vlm"
        self.pipeline_started_at: float = 0.0
        self.pipeline_last_frame_at: float = 0.0
        self.pipeline_restart_count: int = 0

        # @claude VLM load lifecycle — initializing | downloading | compiling | loading | ready | switching | error.
        # @claude `initializing`: right after boot, before entering the precompile stage.
        # @claude `loading`: loading a locally-ready model into memory (download/compile are separate stages).
        self.vlm_state: str = "initializing"
        self.vlm_error: str = ""
        self.vlm_models: list[str] = []
        self.vlm_current_model: str = ""

    def set_vlm_state(self, state: str, error: str = ""):
        """Transition VLM state and push SSE immediately. @claude"""
        with self._lock:
            self.vlm_state = state
            self.vlm_error = error
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

    def set_clip_dir(self, path: str):
        """Set the clip directory for the currently active camera; refreshed on camera switch. @claude"""
        self._clip_dir = path
        self._clip_cache = []
        self._clip_cache_time = 0.0

    def get_clip_dir(self) -> str:
        return self._clip_dir

    def invalidate_clip_cache(self):
        self._clip_cache = []
        self._clip_cache_time = 0.0

    def list_clips(self) -> list[dict]:
        """
        Return every mp4 under the clip directory ({DATA_DIR}/{YYYY}/{MM}/),
        with metadata, newest first, cached with a 5-second TTL.

        @claude
        """
        now = time.time()
        if self._clip_cache and now - self._clip_cache_time < 5.0:
            return self._clip_cache

        if not self._clip_dir:
            return []
        d = Path(self._clip_dir)
        if not d.exists():
            return []

        result = []
        for f in d.rglob("*.mp4"):
            st = f.stat()
            if st.st_size < 10240:
                continue
            entry = {
                "name": f.name,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
                "_mtime": st.st_mtime,
            }
            meta_path = f.with_suffix(".json")
            if meta_path.exists():
                try:
                    with open(meta_path, encoding="utf-8") as mf:
                        meta = json.load(mf)
                    entry["timestamp"] = meta.get("timestamp", int(st.st_mtime))
                    entry["keywords"] = meta.get("keywords", [])
                    entry["vlm_text"] = meta.get("vlm_text", "")
                except Exception:
                    pass
            result.append(entry)
        result.sort(key=lambda x: x["_mtime"], reverse=True)
        self._clip_cache = [{k: v for k, v in r.items() if k != "_mtime"} for r in result]
        self._clip_cache_time = now
        return self._clip_cache

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

    def update_frame(self, frame: Image.Image, orig_w: int, orig_h: int):
        transitioned = False
        with self._lock:
            self.frame   = frame.copy()
            self.frame_w = orig_w
            self.frame_h = orig_h
            now = time.time()
            self.pipeline_last_frame_at = now
            if self.pipeline_started_at == 0.0:
                self.pipeline_started_at = now
            transitioned = self.pipeline_state != "streaming"
            self.pipeline_state = "streaming"
            self.pipeline_status_reason = ""
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

    def _pipeline_snapshot_locked(self) -> dict:
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
            "pipeline_status_reason": self.pipeline_status_reason,
            "pipeline_source_protocol": "rtsp",
            "pipeline_source_transport": "tcp",
            "pipeline_active_for_s": active_for,
            "pipeline_last_frame_age_s": last_frame_age,
            "pipeline_restart_count": self.pipeline_restart_count,
        }

    def mark_pipeline_starting(self, reason: str, restart: bool = False, started_at: float | None = None):
        with self._lock:
            self.pipeline_state = "restarting" if restart else "starting"
            self.pipeline_status_reason = reason
            self.pipeline_started_at = started_at or time.time()
            self.pipeline_last_frame_at = 0.0
            if restart:
                self.pipeline_restart_count += 1
        self._sse_push()

    def mark_pipeline_idle(self, reason: str):
        with self._lock:
            self.pipeline_state = "idle"
            self.pipeline_status_reason = reason
            self.pipeline_started_at = 0.0
            self.pipeline_last_frame_at = 0.0
        self._sse_push()

    def mark_pipeline_stalled(self, reason: str):
        with self._lock:
            self.pipeline_state = "stalled"
            self.pipeline_status_reason = reason
        self._sse_push()

    def mark_pipeline_stopped(self, reason: str):
        with self._lock:
            self.pipeline_state = "stopped"
            self.pipeline_status_reason = reason
            self.pipeline_started_at = 0.0
        self._sse_push()

    def _uptime_text(self) -> str:
        uptime_s = int(time.time() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m:02d}m {s:02d}s"

    def _ptz_snapshot(self) -> dict:
        ptz_cur = ptz.get_current()
        ptz_save = ptz.get_saved()
        return {
            "ptz_pan": ptz_cur["pan"],
            "ptz_tilt": ptz_cur["tilt"],
            "ptz_saved_pan": ptz_save["pan"],
            "ptz_saved_tilt": ptz_save["tilt"],
        }

    def snapshot(self) -> dict:
        with self._lock:
            pipeline = self._pipeline_snapshot_locked()
            runtime = self._runtime_snapshot_locked()
            stream = self._stream_snapshot_locked()

        return {
            **pipeline,
            **stream,
            **self._hw.snapshot(),
            **self._ptz_snapshot(),
            **runtime,
            "uptime": self._uptime_text(),
            "clip_count": len(self.list_clips()),
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

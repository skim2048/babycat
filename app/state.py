"""
App 공유 상태

GStreamer 콜백 / 추론 워커에서 업데이트, HTTP 서버에서 읽기.
"""

import io
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from hardware import HardwareMonitor
import ptz


class AppState:
    """파이프라인 ↔ HTTP 서버 간 공유 상태."""

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
        self._cam_base_dir: str = ""
        self._clip_cache: list[dict] = []
        self._clip_cache_time: float = 0.0

    def set_refs(self, ring, ring_size: int, config: dict):
        self._ring      = ring
        self._ring_size = ring_size
        self._config    = config

    def set_clip_dir(self, path: str):
        """현재 활성 카메라의 클립 디렉토리 설정. 카메라 전환 시 갱신된다."""
        self._clip_dir = path
        self._clip_cache = []
        self._clip_cache_time = 0.0

    def get_clip_dir(self) -> str:
        return self._clip_dir

    def set_cam_base_dir(self, path: str):
        """모든 카메라 클립의 베이스 디렉토리 설정 ({base}/{camera_name}/ 구조)."""
        self._cam_base_dir = path

    def get_cam_base_dir(self) -> str:
        return self._cam_base_dir

    def list_all_clips(self) -> list[dict]:
        """
        모든 카메라 디렉토리의 클립을 조회한다 (API 서버용).

        반환 형식: [{"name": "clip.mp4", "size": 12345, "camera": "mycam"}, ...]
        카메라별 디렉토리는 {_cam_base_dir}/{camera_name}/ 구조이며,
        현재 활성 카메라뿐 아니라 과거 카메라의 클립도 모두 포함한다.
        """
        if not self._cam_base_dir:
            return []
        base = Path(self._cam_base_dir)
        if not base.exists():
            return []

        result = []
        for cam_dir in base.iterdir():
            if not cam_dir.is_dir():
                continue
            cam_name = cam_dir.name
            for f in cam_dir.glob("*.mp4"):
                st = f.stat()
                if st.st_size >= 10240:
                    result.append({
                        "name": f.name,
                        "size": st.st_size,
                        "camera": cam_name,
                        "_mtime": st.st_mtime,
                    })
        result.sort(key=lambda x: x["_mtime"], reverse=True)
        return [{"name": r["name"], "size": r["size"], "camera": r["camera"]}
                for r in result]

    def list_clips(self) -> list[dict]:
        """클립 디렉토리의 mp4 파일 목록 반환 (최신순, 5초 TTL 캐시)."""
        now = time.time()
        if self._clip_cache and now - self._clip_cache_time < 5.0:
            return self._clip_cache

        if not self._clip_dir:
            return []
        d = Path(self._clip_dir)
        if not d.exists():
            return []

        result = []
        for f in d.glob("*.mp4"):
            st = f.stat()
            if st.st_size >= 10240:
                result.append({"name": f.name, "size": st.st_size, "_mtime": st.st_mtime})
        result.sort(key=lambda x: x["_mtime"], reverse=True)
        self._clip_cache = [{"name": r["name"], "size": r["size"]} for r in result]
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
        with self._lock:
            self.frame   = frame.copy()
            self.frame_w = orig_w
            self.frame_h = orig_h

    def update_inference(self, label: str, raw: str, elapsed_ms: float,
                         event_triggered: bool = False):
        with self._lock:
            self.infer_label = label
            self.infer_raw   = raw
            self.infer_ms    = elapsed_ms
            self.event_triggered = event_triggered
        with self._sse_lock:
            queues = list(self._sse_queues)
        for q in queues:
            try:
                q.put_nowait(True)
            except queue.Full:
                pass

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            if self.frame is None:
                return None
            buf = io.BytesIO()
            self.frame.save(buf, format="JPEG", quality=80)
            return buf.getvalue()

    def snapshot(self) -> dict:
        with self._lock:
            pipeline = {
                "frame_w":     self.frame_w,
                "frame_h":     self.frame_h,
                "infer_label": self.infer_label,
                "infer_raw":   self.infer_raw,
                "infer_ms":    round(self.infer_ms, 1),
            }

        uptime_s = int(time.time() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s   = divmod(rem, 60)

        ptz_cur  = ptz.get_current()
        ptz_save = ptz.get_saved()

        hw = self._hw.snapshot()

        return {
            **pipeline,
            **hw,
            "ring_len":      len(self._ring) if self._ring is not None else 0,
            "ring_size":     self._ring_size,
            "uptime":        f"{h}h {m:02d}m {s:02d}s",
            "ptz_pan":       ptz_cur["pan"],
            "ptz_tilt":      ptz_cur["tilt"],
            "ptz_saved_pan":  ptz_save["pan"],
            "ptz_saved_tilt": ptz_save["tilt"],
            "inference_prompt": self.inference_prompt,
            "trigger_keywords": ",".join(self.trigger_keywords),
            "event_triggered": self.event_triggered,
            "clip_count": len(self.list_clips()),
            **{f"cfg_{k}": v for k, v in self._config.items()},
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

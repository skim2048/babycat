"""
Wally-backend — 디버그 대시보드 (stdlib only, 외부 의존성 없음)
파이프라인 점검용: VLM 입력 프레임 + 추론 결과 + 하드웨어 상태를 브라우저에서 실시간 확인

엔드포인트:
  GET  /            HTML 대시보드
  GET  /stream      MJPEG 스트림 (VLM 입력 프레임)
  GET  /events      SSE (추론 결과 + 하드웨어 상태 실시간)
  POST /ptz         PTZ 제어 (move / stop / absolute / save)
  POST /event       이벤트 테스트 (alert / clip) — 검증용
"""

import base64
import datetime
import hashlib
import io
import json
import os
import queue
import re
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from PIL import Image

# ── ONVIF PTZ ─────────────────────────────────────────────────────────────────

_ONVIF_URL   = "http://192.168.1.101:2020/onvif/service"
_ONVIF_USER  = "tapoadmin"
_ONVIF_PASS  = "ace4421000!"
_PTZ_PROFILE = "profile_1"
_PTZ_SPEED   = 0.5          # ContinuousMove 속도 (-1.0 ~ 1.0)
_PTZ_HOME_FILE = "/app/ptz_home.txt"  # 저장 위치 파일 (호스트: src/app/ptz_home.txt)

_ptz_lock   = threading.Lock()
_ptz_current: dict = {"pan": None, "tilt": None}   # 폴링으로 갱신
_ptz_saved:   dict = {"pan": None, "tilt": None}   # 파일에서 로드


def _onvif_auth_header() -> str:
    nonce_raw = os.urandom(20)
    nonce_b64 = base64.b64encode(nonce_raw).decode()
    created   = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    digest    = base64.b64encode(
        hashlib.sha1(nonce_raw + created.encode() + _ONVIF_PASS.encode()).digest()
    ).decode()
    return (
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
        ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{_ONVIF_USER}</wsse:Username>"
        f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>'
        f'<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>'
        f"<wsu:Created>{created}</wsu:Created>"
        "</wsse:UsernameToken></wsse:Security>"
    )


def _onvif_post(body: str) -> str:
    soap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        f"<s:Header>{_onvif_auth_header()}</s:Header>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    )
    req = urllib.request.Request(
        _ONVIF_URL,
        data=soap.encode(),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.read().decode()


def ptz_move(pan: float, tilt: float) -> None:
    """ContinuousMove — 버튼을 누르는 동안 이동."""
    body = (
        f'<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        f'<Velocity><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.2f}" y="{tilt:.2f}"/></Velocity>'
        f"</ContinuousMove>"
    )
    try:
        _onvif_post(body)
    except Exception as e:
        print(f"[PTZ] move 실패: {e}", flush=True)


def ptz_stop() -> None:
    """ContinuousMove 정지."""
    body = (
        f'<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        "<PanTilt>true</PanTilt><Zoom>false</Zoom>"
        "</Stop>"
    )
    try:
        _onvif_post(body)
    except Exception as e:
        print(f"[PTZ] stop 실패: {e}", flush=True)


def ptz_absolute_move(pan: float, tilt: float) -> None:
    """AbsoluteMove — 저장된 위치로 이동."""
    body = (
        f'<AbsoluteMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        f'<Position><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.3f}" y="{tilt:.3f}"/></Position>'
        f"</AbsoluteMove>"
    )
    try:
        _onvif_post(body)
    except Exception as e:
        print(f"[PTZ] absolute move 실패: {e}", flush=True)


def ptz_get_status() -> Optional[dict]:
    """GetStatus로 현재 Pan/Tilt 위치 조회."""
    body = (
        f'<GetStatus xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        "</GetStatus>"
    )
    try:
        text = _onvif_post(body)
        m = re.search(r'PanTilt[^/]* x="([^"]*)"[^/]* y="([^"]*)"', text)
        if m:
            return {"pan": round(float(m.group(1)), 3),
                    "tilt": round(float(m.group(2)), 3)}
    except Exception as e:
        print(f"[PTZ] GetStatus 실패: {e}", flush=True)
    return None


def ptz_load_home() -> None:
    """앱 시작 시 저장 파일에서 홈 위치 로드."""
    global _ptz_saved
    try:
        with open(_PTZ_HOME_FILE) as f:
            data = dict(line.strip().split("=") for line in f if "=" in line)
        with _ptz_lock:
            _ptz_saved = {
                "pan":  round(float(data["pan"]),  3),
                "tilt": round(float(data["tilt"]), 3),
            }
        print(f"[PTZ] 저장 위치 로드: {_ptz_saved}", flush=True)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[PTZ] 저장 위치 로드 실패: {e}", flush=True)


def ptz_save_home() -> bool:
    """현재 폴링된 위치를 파일에 저장. 성공 여부 반환."""
    with _ptz_lock:
        cur = dict(_ptz_current)
    if cur["pan"] is None:
        return False
    try:
        with open(_PTZ_HOME_FILE, "w") as f:
            f.write(f"pan={cur['pan']}\ntilt={cur['tilt']}\n")
        with _ptz_lock:
            _ptz_saved.update(cur)
        print(f"[PTZ] 위치 저장: pan={cur['pan']}, tilt={cur['tilt']}", flush=True)
        return True
    except Exception as e:
        print(f"[PTZ] 위치 저장 실패: {e}", flush=True)
        return False


def _ptz_poll_loop() -> None:
    """백그라운드 스레드: 2초마다 현재 PTZ 위치 폴링."""
    while True:
        status = ptz_get_status()
        if status:
            with _ptz_lock:
                _ptz_current.update(status)
        time.sleep(2)


# ── 하드웨어 모니터 ───────────────────────────────────────────────────────────

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
    """Jetson Orin NX 하드웨어 상태를 /proc, /sys에서 읽기."""

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


# ── 공유 상태 ─────────────────────────────────────────────────────────────────

class DebugState:
    """GStreamer 콜백 / 추론 워커에서 업데이트, 디버그 서버에서 읽기."""

    def __init__(self):
        self._lock = threading.Lock()
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
        self._judge     = None
        self._config:   dict  = {}

        # TODO: 리팩토링 시 main.py 의존성 역전 고려 (현재 main→debug 단방향 콜백으로 임시 해결)
        self._send_alert    = None
        self._preserve_clip = None
        self._last_event:   str = ""

        self._sse_queues: list[queue.Queue] = []

    def set_refs(self, ring, ring_size: int, judge, config: dict,
                 send_alert_fn=None, preserve_clip_fn=None):
        self._ring          = ring
        self._ring_size     = ring_size
        self._judge         = judge
        self._config        = config
        self._send_alert    = send_alert_fn
        self._preserve_clip = preserve_clip_fn

    def update_frame(self, frame: Image.Image, orig_w: int, orig_h: int):
        with self._lock:
            self.frame   = frame.copy()
            self.frame_w = orig_w
            self.frame_h = orig_h

    def update_inference(self, label: str, raw: str, elapsed_ms: float):
        with self._lock:
            self.infer_label = label
            self.infer_raw   = raw
            self.infer_ms    = elapsed_ms
        for q in list(self._sse_queues):
            try:
                q.put_nowait(True)
            except queue.Full:
                pass

    def update_event_result(self, msg: str):
        with self._lock:
            self._last_event = msg
        for q in list(self._sse_queues):
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
                "last_event":  self._last_event,
            }

        judge_streak = ""
        if self._judge is not None:
            s = self._judge._streak
            if s:
                key, count = next(iter(s.items()))
                judge_streak = f"{key} ({count}/{self._judge._consec_n})"

        uptime_s = int(time.time() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s   = divmod(rem, 60)

        with _ptz_lock:
            ptz_cur  = dict(_ptz_current)
            ptz_save = dict(_ptz_saved)

        hw = self._hw.snapshot()

        return {
            **pipeline,
            **hw,
            "ring_len":      len(self._ring) if self._ring is not None else 0,
            "ring_size":     self._ring_size,
            "judge_streak":  judge_streak,
            "uptime":        f"{h}h {m:02d}m {s:02d}s",
            "ptz_pan":       ptz_cur["pan"],
            "ptz_tilt":      ptz_cur["tilt"],
            "ptz_saved_pan":  ptz_save["pan"],
            "ptz_saved_tilt": ptz_save["tilt"],
            **{f"cfg_{k}": v for k, v in self._config.items()},
        }

    def sse_subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1)
        self._sse_queues.append(q)
        return q

    def sse_unsubscribe(self, q: queue.Queue):
        try:
            self._sse_queues.remove(q)
        except ValueError:
            pass


state = DebugState()


# ── HTML 대시보드 ─────────────────────────────────────────────────────────────

HTML_PAGE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Wally-backend Debug</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Courier New', monospace; background: #f5f5f5; color: #333; }
.header { background: #fff; padding: 12px 20px; border-bottom: 1px solid #ddd;
          display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 16px; color: #2a7a2a; }
.header .uptime { font-size: 12px; color: #999; }
.main { display: flex; height: calc(100vh - 45px); overflow: hidden; }
.video-area { flex: 1; min-width: 0; padding: 12px; }
.video-box video { width: 100%; display: block;
                   border: 1px solid #ddd; background: #000; border-radius: 4px; }
.video-label { font-size: 11px; color: #333; font-weight: bold;
               text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
.dash { width: 340px; flex-shrink: 0; overflow-y: auto; border-left: 1px solid #ddd;
        padding: 12px; display: flex; flex-direction: column; gap: 10px; }

/* ── 아코디언 섹션 ── */
.section { background: #fff; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden; }
.section-title {
  font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 1px;
  padding: 8px 12px; cursor: pointer; user-select: none;
  display: flex; justify-content: space-between; align-items: center;
  background: #fafafa; border-bottom: 1px solid #e0e0e0;
}
.section-title:hover { background: #f0f0f0; }
.section-title .arrow { font-size: 10px; color: #aaa; transition: transform 0.2s; }
.section.collapsed .section-title .arrow { transform: rotate(-90deg); }
.section-body { padding: 10px 12px; }
.section.collapsed .section-body { display: none; }

.row { display: flex; justify-content: space-between; align-items: baseline; padding: 3px 0; }
.row .k { font-size: 12px; color: #888; }
.row .v { font-size: 14px; font-weight: bold; color: #333; }
.infer-img { width: 100%; display: block;
             border: 1px solid #ddd; background: #000; border-radius: 4px; }
.result-box { padding: 8px; border-radius: 4px; margin-top: 4px; }
.result-box.normal { background: #eef6ee; border: 1px solid #b5d8b5; }
.result-box.alert  { background: #f6eeee; border: 1px solid #d8b5b5; }
.result-label { font-size: 20px; font-weight: bold; }
.result-label.normal { color: #2a7a2a; }
.result-label.alert  { color: #cc3333; }
.result-raw { font-size: 14px; font-weight: bold; color: #333; margin-top: 4px; }
.bar-bg { height: 6px; background: #e0e0e0; border-radius: 3px; margin-top: 3px; }
.bar-fg { height: 100%; border-radius: 3px; transition: width 0.5s; }
.bar-cpu .bar-fg { background: #5599cc; }
.bar-ram .bar-fg { background: #cc9955; }
.bar-gpu .bar-fg { background: #77aa44; }
.temp { display: inline-block; padding: 2px 6px; border-radius: 3px;
        font-size: 12px; font-weight: bold; }
.temp.cool { background: #eef6ee; color: #2a7a2a; }
.temp.warm { background: #f6f3ee; color: #aa8800; }
.temp.hot  { background: #f6eeee; color: #cc3333; }

/* ── PTZ ── */
.ptz-grid { display: grid; grid-template-columns: repeat(3, 48px);
            grid-template-rows: repeat(3, 48px); gap: 4px;
            justify-content: center; margin: 8px 0; }
.ptz-btn { width: 48px; height: 48px; border-radius: 6px;
           border: 1px solid #ccc; background: #f0f0f0;
           font-size: 20px; cursor: pointer; user-select: none;
           display: flex; align-items: center; justify-content: center;
           transition: background 0.1s; -webkit-tap-highlight-color: transparent; }
.ptz-btn:active, .ptz-btn.pressing { background: #d0e8ff; border-color: #5599cc; }
.ptz-btn.stop { background: #fff0f0; border-color: #d8b5b5; font-size: 14px; color: #cc3333; }
.ptz-info { font-size: 12px; color: #555; margin: 6px 0 2px; }
.ptz-info span { font-weight: bold; color: #333; }
.ptz-saved-row { display: flex; align-items: center; gap: 6px; margin-top: 8px;
                 padding-top: 8px; border-top: 1px solid #eee; }
.ptz-saved-val { font-size: 12px; color: #555; flex: 1; }
.ptz-saved-val span { font-weight: bold; color: #333; }
.ptz-action-btn { font-size: 11px; padding: 4px 8px; border-radius: 4px;
                  border: 1px solid #ccc; background: #f5f5f5; cursor: pointer;
                  white-space: nowrap; }
.ptz-action-btn:hover { background: #e8e8e8; }
.ptz-action-btn.go { background: #eef6ee; border-color: #b5d8b5; color: #2a7a2a; }
.ptz-action-btn.go:hover { background: #d8efd8; }
.ptz-status-txt { font-size: 11px; color: #aaa; text-align: center; margin-top: 6px; }

/* ── Events ── */
.ev-row { display: flex; gap: 6px; margin-bottom: 8px; }
.ev-select { flex: 1; font-size: 12px; padding: 4px 6px; border: 1px solid #ccc;
             border-radius: 4px; background: #fafafa; }
.ev-btn-row { display: flex; gap: 6px; }
</style>
</head>
<body>
<div class="header">
  <h1>Wally-backend Pipeline Debug</h1>
  <span class="uptime" id="v-uptime">-</span>
</div>
<div class="main">
  <div class="video-area">
    <div class="video-box">
      <div class="video-label">Live Stream</div>
      <video id="live-stream" autoplay muted playsinline></video>
    </div>
  </div>
  <div class="dash">

    <!-- Inference -->
    <div class="section" id="sec-inference">
      <div class="section-title" onclick="toggleSection('sec-inference')">
        Inference <span class="arrow">▼</span>
      </div>
      <div class="section-body">
        <img class="infer-img" id="stream" src="/stream" alt="VLM input" />
        <div class="result-box normal" id="result-box" style="margin-top:8px;">
          <div class="result-label normal" id="v-result">대기 중</div>
          <div class="result-raw" id="v-raw"></div>
        </div>
        <div style="margin-top:8px;">
          <div class="row">
            <span class="k">추론 당 소요 시간</span>
            <span class="v" id="v-infer-time">-</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Pipeline -->
    <div class="section" id="sec-pipeline">
      <div class="section-title" onclick="toggleSection('sec-pipeline')">
        Pipeline <span class="arrow">▼</span>
      </div>
      <div class="section-body">
        <div class="row">
          <span class="k">원본 해상도</span>
          <span class="v" id="v-resolution">-</span>
        </div>
        <div class="row">
          <span class="k">N_FRAMES</span>
          <span class="v" id="v-nframes">-</span>
        </div>
      </div>
    </div>

    <!-- Hardware -->
    <div class="section" id="sec-hardware">
      <div class="section-title" onclick="toggleSection('sec-hardware')">
        Hardware <span class="arrow">▼</span>
      </div>
      <div class="section-body">
        <div class="row">
          <span class="k">CPU</span>
          <span class="v" id="v-cpu">0%</span>
        </div>
        <div class="bar-bg bar-cpu"><div class="bar-fg" id="bar-cpu" style="width:0%"></div></div>
        <div class="row" style="margin-top:8px;">
          <span class="k">RAM</span>
          <span class="v" id="v-ram">0 / 0 MB</span>
        </div>
        <div class="bar-bg bar-ram"><div class="bar-fg" id="bar-ram" style="width:0%"></div></div>
        <div class="row" style="margin-top:8px;">
          <span class="k">GPU</span>
          <span class="v" id="v-gpu">0%</span>
        </div>
        <div class="bar-bg bar-gpu"><div class="bar-fg" id="bar-gpu" style="width:0%"></div></div>
        <div class="row" style="margin-top:10px;">
          <span class="k">CPU Temp</span>
          <span class="temp cool" id="v-cpu-temp">-</span>
        </div>
        <div class="row" style="margin-top:4px;">
          <span class="k">GPU Temp</span>
          <span class="temp cool" id="v-gpu-temp">-</span>
        </div>
      </div>
    </div>

    <!-- Pan / Tilt -->
    <div class="section" id="sec-ptz">
      <div class="section-title" onclick="toggleSection('sec-ptz')">
        Pan / Tilt <span class="arrow">▼</span>
      </div>
      <div class="section-body">
        <!-- 현재 위치 -->
        <div class="ptz-info">현재 위치 &nbsp; Pan: <span id="v-ptz-pan">-</span> &nbsp; Tilt: <span id="v-ptz-tilt">-</span></div>

        <!-- 방향 버튼 -->
        <div class="ptz-grid">
          <div></div>
          <button class="ptz-btn" id="ptz-up"    data-pan="0"  data-tilt="1">▲</button>
          <div></div>
          <button class="ptz-btn" id="ptz-left"  data-pan="-1" data-tilt="0">◀</button>
          <button class="ptz-btn stop" id="ptz-stop">■</button>
          <button class="ptz-btn" id="ptz-right" data-pan="1"  data-tilt="0">▶</button>
          <div></div>
          <button class="ptz-btn" id="ptz-down"  data-pan="0"  data-tilt="-1">▼</button>
          <div></div>
        </div>

        <!-- 저장 / 이동 -->
        <div class="ptz-saved-row">
          <div class="ptz-saved-val">저장 &nbsp; Pan: <span id="v-saved-pan">-</span> &nbsp; Tilt: <span id="v-saved-tilt">-</span></div>
          <button class="ptz-action-btn" id="btn-save-pos">현재 저장</button>
          <button class="ptz-action-btn go" id="btn-goto-pos">저장 위치로</button>
        </div>

        <div class="ptz-status-txt" id="ptz-status">대기</div>
      </div>
    </div>

    <!-- Events -->
    <div class="section" id="sec-events">
      <div class="section-title" onclick="toggleSection('sec-events')">
        Events <span class="arrow">▼</span>
      </div>
      <div class="section-body">
        <div class="ev-row">
          <select class="ev-select" id="ev-behavior"></select>
        </div>
        <div class="ev-btn-row">
          <button class="ptz-action-btn" id="btn-ev-alert">알림 발송</button>
          <button class="ptz-action-btn go" id="btn-ev-clip">클립 저장</button>
        </div>
        <div class="ptz-status-txt" id="ev-status">대기</div>
      </div>
    </div>

  </div>
</div>

<script>
// ── 아코디언 ──────────────────────────────────────────────────────────────────
function toggleSection(id) {
  document.getElementById(id).classList.toggle('collapsed');
}

// ── 온도 클래스 ───────────────────────────────────────────────────────────────
function tempClass(c) {
  if (c >= 80) return "temp hot";
  if (c >= 60) return "temp warm";
  return "temp cool";
}

// ── Live Stream (HLS) ─────────────────────────────────────────────────────────
(function() {
  const hlsUrl = "http://" + window.location.hostname + ":8888/live/index.m3u8";
  const video  = document.getElementById("live-stream");
  function tryPlay() { video.play().catch(function() {}); }
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = hlsUrl;
    video.addEventListener("loadedmetadata", tryPlay);
  } else {
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/hls.js@latest";
    script.onload = function() {
      if (!Hls.isSupported()) return;
      function initHls() {
        const hls = new Hls({ liveSyncDurationCount:1, liveMaxLatencyDurationCount:3,
                               lowLatencyMode:true, backBufferLength:0 });
        hls.loadSource(hlsUrl);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, tryPlay);
        hls.on(Hls.Events.ERROR, function(_, data) {
          if (data.fatal) { hls.destroy(); setTimeout(initHls, 3000); }
        });
      }
      initHls();
    };
    document.head.appendChild(script);
  }
})();

// ── SSE ───────────────────────────────────────────────────────────────────────
const es = new EventSource("/events");
es.onmessage = function(e) {
  const d = JSON.parse(e.data);

  document.getElementById("v-uptime").textContent = d.uptime;

  // Inference
  const label   = d.infer_label || "대기 중";
  const isAlert = label !== "정상" && label !== "대기 중";
  document.getElementById("v-result").textContent  = label;
  document.getElementById("v-result").className    = "result-label " + (isAlert ? "alert" : "normal");
  document.getElementById("result-box").className  = "result-box "   + (isAlert ? "alert" : "normal");
  document.getElementById("v-raw").textContent     = d.infer_raw || "";
  document.getElementById("v-infer-time").textContent = d.infer_ms + " ms";

  // Pipeline
  document.getElementById("v-resolution").textContent = d.frame_w + " x " + d.frame_h;
  if (d.cfg_n_frames !== undefined)
    document.getElementById("v-nframes").textContent = d.cfg_n_frames;

  // Hardware
  document.getElementById("v-cpu").textContent     = d.cpu_percent + "%";
  document.getElementById("bar-cpu").style.width   = d.cpu_percent + "%";
  const ramPct = d.ram_total_mb > 0 ? ((d.ram_used_mb / d.ram_total_mb) * 100).toFixed(0) : 0;
  document.getElementById("v-ram").textContent     = d.ram_used_mb + " / " + d.ram_total_mb + " MB";
  document.getElementById("bar-ram").style.width   = ramPct + "%";
  document.getElementById("v-gpu").textContent     = d.gpu_load + "%";
  document.getElementById("bar-gpu").style.width   = d.gpu_load + "%";
  const cpuT = document.getElementById("v-cpu-temp");
  cpuT.textContent = d.cpu_temp + " C"; cpuT.className = tempClass(d.cpu_temp);
  const gpuT = document.getElementById("v-gpu-temp");
  gpuT.textContent = d.gpu_temp + " C"; gpuT.className = tempClass(d.gpu_temp);

  // PTZ 현재/저장 위치
  const fmt = function(v) { return v !== null && v !== undefined ? v.toFixed(3) : "-"; };
  document.getElementById("v-ptz-pan").textContent   = fmt(d.ptz_pan);
  document.getElementById("v-ptz-tilt").textContent  = fmt(d.ptz_tilt);
  document.getElementById("v-saved-pan").textContent  = fmt(d.ptz_saved_pan);
  document.getElementById("v-saved-tilt").textContent = fmt(d.ptz_saved_tilt);

  // Events
  if (d.cfg_behaviors) window._initBehaviors(d.cfg_behaviors);
  if (d.last_event)    document.getElementById("ev-status").textContent = d.last_event;
};

// ── 이벤트 테스트 ─────────────────────────────────────────────────────────────
(function() {
  var behaviorsLoaded = false;
  var select = document.getElementById("ev-behavior");
  var status = document.getElementById("ev-status");

  window._initBehaviors = function(behaviors) {
    if (behaviorsLoaded) return;
    behaviorsLoaded = true;
    Object.keys(behaviors).forEach(function(key) {
      var opt = document.createElement("option");
      opt.value = key;
      opt.textContent = behaviors[key] + " (" + key + ")";
      select.appendChild(opt);
    });
  };

  function eventPost(action) {
    return fetch("/event", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action: action, behavior: select.value || "test"})
    }).then(function(r) { return r.json(); });
  }

  document.getElementById("btn-ev-alert").addEventListener("click", function() {
    status.textContent = "발송 중...";
    eventPost("alert").then(function(r) {
      status.textContent = r.ok ? r.msg : "실패: " + r.msg;
    });
  });

  document.getElementById("btn-ev-clip").addEventListener("click", function() {
    status.textContent = "저장 중...";
    eventPost("clip").then(function(r) {
      status.textContent = r.ok ? r.msg : "실패: " + r.msg;
    });
  });
})();

// ── PTZ 제어 ──────────────────────────────────────────────────────────────────
(function() {
  const SPEED  = 0.5;
  const status = document.getElementById("ptz-status");

  function ptzPost(body) {
    return fetch("/ptz", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    });
  }

  function startMove(btn) {
    const pan  = parseFloat(btn.dataset.pan)  * SPEED;
    const tilt = parseFloat(btn.dataset.tilt) * SPEED;
    btn.classList.add("pressing");
    status.textContent = (pan > 0 ? "→ 오른쪽" : pan < 0 ? "← 왼쪽" :
                          tilt > 0 ? "↑ 위"    : "↓ 아래") + " 이동 중";
    ptzPost({action: "move", pan: pan, tilt: tilt});
  }

  function stopMove(btn) {
    btn.classList.remove("pressing");
    status.textContent = "정지";
    ptzPost({action: "stop"});
  }

  ["ptz-up", "ptz-down", "ptz-left", "ptz-right"].forEach(function(id) {
    const btn = document.getElementById(id);
    btn.addEventListener("mousedown",  function(e) { e.preventDefault(); startMove(btn); });
    btn.addEventListener("mouseup",    function()  { stopMove(btn); });
    btn.addEventListener("mouseleave", function()  { if (btn.classList.contains("pressing")) stopMove(btn); });
    btn.addEventListener("touchstart", function(e) { e.preventDefault(); startMove(btn); }, {passive: false});
    btn.addEventListener("touchend",   function()  { stopMove(btn); });
  });

  document.getElementById("ptz-stop").addEventListener("click", function() {
    status.textContent = "강제 정지";
    ptzPost({action: "stop"});
  });

  // 현재 위치 저장
  document.getElementById("btn-save-pos").addEventListener("click", function() {
    status.textContent = "저장 중...";
    ptzPost({action: "save"}).then(function(r) { return r.json(); }).then(function(r) {
      status.textContent = r.ok ? "저장 완료" : "저장 실패 (위치 미확인)";
    });
  });

  // 저장 위치로 이동
  document.getElementById("btn-goto-pos").addEventListener("click", function() {
    status.textContent = "이동 중...";
    ptzPost({action: "goto"}).then(function(r) { return r.json(); }).then(function(r) {
      status.textContent = r.ok ? "이동 완료" : "저장된 위치 없음";
    });
  });
})();
</script>
</body>
</html>"""


# ── HTTP 핸들러 ───────────────────────────────────────────────────────────────

class DebugHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/stream":
            self._serve_mjpeg()
        elif self.path == "/events":
            self._serve_sse()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/event":
            length   = int(self.headers.get("Content-Length", 0))
            body     = json.loads(self.rfile.read(length) or b"{}")
            action   = body.get("action")
            behavior = body.get("behavior", "test")
            ok  = True
            msg = ""

            if action == "alert":
                if state._send_alert:
                    threading.Thread(
                        target=state._send_alert, args=(behavior,), daemon=True
                    ).start()
                    msg = f"알림 발송: {behavior}"
                else:
                    ok = False; msg = "send_alert 미연결"
            elif action == "clip":
                if state._preserve_clip:
                    threading.Thread(
                        target=state._preserve_clip,
                        args=(behavior, time.time()),
                        daemon=True,
                    ).start()
                    msg = f"클립 저장: {behavior}"
                else:
                    ok = False; msg = "preserve_clip 미연결"
            else:
                ok = False; msg = f"알 수 없는 action: {action}"

            state.update_event_result(msg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "msg": msg}).encode())

        elif self.path == "/ptz":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length) or b"{}")
            action = body.get("action")
            ok     = True

            if action == "move":
                threading.Thread(
                    target=ptz_move,
                    args=(float(body.get("pan", 0)), float(body.get("tilt", 0))),
                    daemon=True,
                ).start()
            elif action == "stop":
                threading.Thread(target=ptz_stop, daemon=True).start()
            elif action == "save":
                ok = ptz_save_home()
            elif action == "goto":
                with _ptz_lock:
                    saved = dict(_ptz_saved)
                if saved["pan"] is not None:
                    threading.Thread(
                        target=ptz_absolute_move,
                        args=(saved["pan"], saved["tilt"]),
                        daemon=True,
                    ).start()
                else:
                    ok = False

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok}).encode())
        else:
            self.send_error(404)

    def _serve_html(self):
        body = HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                jpeg = state.get_jpeg()
                if jpeg:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n".encode())
                    self.wfile.write(b"\r\n")
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = state.sse_subscribe()
        try:
            while True:
                try:
                    q.get(timeout=2)
                except queue.Empty:
                    pass
                snap = state.snapshot()
                self.wfile.write(f"data: {json.dumps(snap, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            state.sse_unsubscribe(q)


# ── 서버 시작 ─────────────────────────────────────────────────────────────────

class ThreadedHTTPServer(HTTPServer):
    daemon_threads = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def start_debug_server(port: int = 8080):
    """별도 데몬 스레드에서 디버그 서버 시작."""
    ptz_load_home()

    threading.Thread(target=_ptz_poll_loop, daemon=True).start()

    server = ThreadedHTTPServer(("0.0.0.0", port), DebugHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[debug] 디버그 대시보드: http://0.0.0.0:{port}", flush=True)

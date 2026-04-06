"""
Babycat — App HTTP 서버

엔드포인트:
  GET  /            HTML 대시보드
  GET  /stream      MJPEG 스트림 (VLM 입력 프레임)
  GET  /events      SSE (추론 결과 + 하드웨어 상태 실시간)
  GET  /clips       클립 목록 (JSON)
  GET  /clip/{name} 클립 파일 다운로드 (Range 지원)
  POST /prompt      VLM 프롬프트/트리거 변경
  POST /ptz         PTZ 제어 (move / stop / save / goto)
  DELETE /clips     클립 선택 삭제
"""

import hashlib
import hmac
import json
import logging
import os
import queue
import re
import threading
import time
import urllib.parse
from base64 import urlsafe_b64decode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import camera
import ptz
from state import state

log = logging.getLogger(__name__)

MAX_BODY = 65536  # 64KB
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")


def _verify_jwt(token: str) -> bool:
    """JWT(HMAC-SHA256) 서명 및 만료 검증."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        header, payload, sig = parts
        expected = hmac.new(
            JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        padding = 4 - len(sig) % 4
        actual = urlsafe_b64decode(sig + "=" * padding)
        if not hmac.compare_digest(actual, expected):
            return False
        padding = 4 - len(payload) % 4
        data = json.loads(urlsafe_b64decode(payload + "=" * padding))
        return data.get("exp", 0) >= time.time()
    except Exception:
        return False


class AppHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _check_auth(self) -> bool:
        """Authorization 헤더 또는 쿼리 파라미터의 토큰 검증. 실패 시 401 응답."""
        # 1) Authorization: Bearer <token>
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and _verify_jwt(auth[7:]):
            return True
        # 2) ?token=<token> (EventSource 등 헤더 설정 불가 클라이언트용)
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        token_list = qs.get("token", [])
        if token_list and _verify_jwt(token_list[0]):
            return True
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"detail": "unauthorized"}).encode())
        return False

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/":
            self._serve_health()
            return
        if not self._check_auth():
            return
        if self.path == "/stream":
            self._serve_mjpeg()
        elif self.path == "/events":
            self._serve_sse()
        elif self.path == "/clips":
            self._serve_clip_list()
        elif self.path.startswith("/clip/"):
            self._serve_clip_file()
        elif self.path == "/camera":
            self._serve_camera()
        else:
            self.send_error(404)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        if not self._check_auth():
            return
        if self.path == "/prompt":
            self._handle_prompt()
        elif self.path == "/ptz":
            self._handle_ptz()
        elif self.path == "/camera":
            self._handle_camera()
        else:
            self.send_error(404)

    # ── DELETE ────────────────────────────────────────────────────────────────

    def do_DELETE(self):
        if not self._check_auth():
            return
        if self.path == "/clips":
            self._handle_clip_delete()
        else:
            self.send_error(404)

    # ── 유틸리티 ──────────────────────────────────────────────────────────────

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            return {}
        if length <= 0 or length > MAX_BODY:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def _send_file_chunk(self, fpath: Path, offset: int, length: int,
                         chunk_size: int = 65536) -> None:
        with open(fpath, "rb") as f:
            f.seek(offset)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    # ── 핸들러 구현 ──────────────────────────────────────────────────────────

    def _serve_health(self):
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
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
                    q.get(timeout=1)
                except queue.Empty:
                    pass
                snap = state.snapshot()
                self.wfile.write(f"data: {json.dumps(snap, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            state.sse_unsubscribe(q)

    def _serve_clip_list(self):
        clips = state.list_clips()
        body = json.dumps(clips, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_clip_file(self):
        raw = self.path[len("/clip/"):]
        name = urllib.parse.unquote(raw.split("?", 1)[0])
        if "/" in name or "\\" in name or ".." in name:
            self.send_error(400)
            return
        clip_dir = state.get_clip_dir()
        if not clip_dir:
            self.send_error(404)
            return
        fpath = Path(clip_dir) / name
        if not fpath.exists() or not fpath.is_file():
            self.send_error(404)
            return

        file_size = fpath.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if not m:
                self.send_error(416)
                return
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self._send_file_chunk(fpath, start, length)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self._send_file_chunk(fpath, 0, file_size)

    def _handle_prompt(self):
        body = self._read_json_body()
        prompt = body.get("prompt", "").strip()
        triggers_raw = body.get("triggers", "").strip()
        if prompt:
            state.set_prompt(prompt)
            log.info("Prompt changed: %s", prompt[:80])
        keywords = [k.strip().lower() for k in triggers_raw.split(",") if k.strip()]
        state.set_triggers(keywords)
        if keywords:
            log.info("Trigger keywords: %s", keywords)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": bool(prompt)}).encode())

    def _handle_ptz(self):
        body = self._read_json_body()
        action = body.get("action")
        ok     = True

        if action == "move":
            try:
                pan = float(body.get("pan", 0))
                tilt = float(body.get("tilt", 0))
            except (ValueError, TypeError):
                self.send_error(400, "invalid pan/tilt values")
                return
            ptz.set_moving(True)
            threading.Thread(
                target=ptz.move, args=(pan, tilt), daemon=True,
            ).start()
        elif action == "stop":
            ptz.set_moving(False)
            threading.Thread(target=ptz.stop, daemon=True).start()
        elif action == "save":
            home = ptz.save_home()
            if home:
                camera.save({"ptz_home": home})
            ok = home is not None
        elif action == "goto":
            saved = ptz.get_saved()
            if saved["pan"] is not None:
                threading.Thread(
                    target=ptz.absolute_move,
                    args=(saved["pan"], saved["tilt"]),
                    daemon=True,
                ).start()
            else:
                ok = False

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": ok}).encode())

    def _serve_camera(self):
        config = camera.load()
        if config:
            result = {"configured": True, **config}
        else:
            result = {"configured": False}
        body = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_camera(self):
        body = self._read_json_body()
        result = camera.apply(body)
        # 카메라 전환 시 클립 저장 디렉토리를 새 카메라 경로로 갱신
        if result.get("ok") and result.get("clip_dir"):
            state.set_clip_dir(result["clip_dir"])
            log.info("Clip directory switched to: %s", result["clip_dir"])
        resp = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def _handle_clip_delete(self):
        body = self._read_json_body()
        names = body.get("names", [])
        clip_dir = state.get_clip_dir()
        deleted = 0
        if clip_dir:
            for name in names:
                if "/" in name or "\\" in name or ".." in name:
                    continue
                fpath = Path(clip_dir) / name
                if fpath.exists() and fpath.is_file():
                    fpath.unlink()
                    deleted += 1
        log.info("Clips deleted: %d", deleted)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "deleted": deleted}).encode())


# ── 서버 시작 ────────────────────────────────────────────────────────────────

def start_server(port: int = 8080):
    """별도 데몬 스레드에서 App HTTP 서버 시작."""
    config = camera.load()
    ptz.load_home(config.get("ptz_home") if config else None)

    threading.Thread(target=ptz.poll_loop, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", port), AppHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("App HTTP server: http://0.0.0.0:%d", port)

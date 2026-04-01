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

import json
import os
import queue
import re
import threading
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import camera
import ptz
from state import state


_DASHBOARD_HTML: str = ""


def _load_dashboard() -> None:
    global _DASHBOARD_HTML
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, encoding="utf-8") as f:
        _DASHBOARD_HTML = f.read()


class AppHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/stream":
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
        if self.path == "/clips":
            self._handle_clip_delete()
        else:
            self.send_error(404)

    # ── 핸들러 구현 ──────────────────────────────────────────────────────────

    def _serve_html(self):
        body = _DASHBOARD_HTML.encode("utf-8")
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
        clip_dir = state._clip_dir
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
            with open(fpath, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(length))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(fpath, "rb") as f:
                self.wfile.write(f.read())

    def _handle_prompt(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        prompt = body.get("prompt", "").strip()
        triggers_raw = body.get("triggers", "").strip()
        if prompt:
            state.set_prompt(prompt)
            print(f"[prompt] 프롬프트 변경: {prompt[:80]}", flush=True)
        keywords = [k.strip().lower() for k in triggers_raw.split(",") if k.strip()]
        state.set_triggers(keywords)
        if keywords:
            print(f"[prompt] 트리거 키워드: {keywords}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": bool(prompt)}).encode())

    def _handle_ptz(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")
        action = body.get("action")
        ok     = True

        if action == "move":
            ptz.set_moving(True)
            threading.Thread(
                target=ptz.move,
                args=(float(body.get("pan", 0)), float(body.get("tilt", 0))),
                daemon=True,
            ).start()
        elif action == "stop":
            ptz.set_moving(False)
            threading.Thread(target=ptz.stop, daemon=True).start()
        elif action == "save":
            ok = ptz.save_home()
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
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        result = camera.apply(body)
        resp = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def _handle_clip_delete(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        names = body.get("names", [])
        clip_dir = state._clip_dir
        deleted = 0
        if clip_dir:
            for name in names:
                if "/" in name or "\\" in name or ".." in name:
                    continue
                fpath = Path(clip_dir) / name
                if fpath.exists() and fpath.is_file():
                    fpath.unlink()
                    deleted += 1
        print(f"[clip] 삭제: {deleted}개", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "deleted": deleted}).encode())


# ── 서버 시작 ────────────────────────────────────────────────────────────────

class _ThreadedHTTPServer(HTTPServer):
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


def start_server(port: int = 8080):
    """별도 데몬 스레드에서 App HTTP 서버 시작."""
    _load_dashboard()
    ptz.load_home()

    threading.Thread(target=ptz.poll_loop, daemon=True).start()

    server = _ThreadedHTTPServer(("0.0.0.0", port), AppHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[server] App HTTP 서버: http://0.0.0.0:{port}", flush=True)

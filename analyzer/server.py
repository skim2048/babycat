"""
Babycat analyzer — internal HTTP server.

Internal only: the container publishes no port; the router is the sole
HTTP caller (SDD §6.3). No authentication — requests that reach here
already passed the router.

Endpoints:
  GET  /            Health check
  GET  /events      SSE (inference results + pipeline/VLM state)
  GET  /stream      MJPEG stream (VLM input frames)
  POST /prompt      Change VLM prompt / trigger keywords
  POST /start       Start or restart analysis (FR-024)
  POST /vlm/switch  Request VLM model switch

@claude
"""

import json
import logging
import queue
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

import settings
from state import state as app_state

log = logging.getLogger(__name__)

_start_analysis_callback: Callable[[], bool] | None = None

MAX_BODY = 65536  # @claude 64KB cap on request bodies.


def set_start_analysis_callback(callback: Callable[[], bool]) -> None:
    """Register the analysis-start callback from the live main module."""
    global _start_analysis_callback
    _start_analysis_callback = callback


def snapshot_sse_message() -> bytes:
    try:
        snap = app_state.snapshot()
    except Exception:
        log.exception("SSE snapshot failed")
        return b": snapshot_unavailable\n\n"
    return f"data: {json.dumps(snap, ensure_ascii=False)}\n\n".encode()


def persist_settings() -> None:
    settings.save(
        app_state.get_prompt(), app_state.get_triggers(), app_state.is_analysis_active()
    )


class AnalyzerHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._send_json({"status": "ok"})
        elif path == "/stream":
            self._serve_mjpeg()
        elif path == "/events":
            self._serve_sse()
        else:
            self.send_error(404)

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/prompt":
            self._handle_prompt()
        elif path == "/start":
            self._handle_start()
        elif path == "/vlm/switch":
            self._handle_vlm_switch()
        else:
            self.send_error(404)

    # ── Utilities ────────────────────────────────────────────────────────────

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

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── Handler implementations ──────────────────────────────────────────────

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                jpeg = app_state.get_jpeg()
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
        q = app_state.sse_subscribe()
        try:
            while True:
                try:
                    q.get(timeout=1)
                except queue.Empty:
                    pass
                self.wfile.write(snapshot_sse_message())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            app_state.sse_unsubscribe(q)

    def _handle_prompt(self):
        """Store the prompt and keywords. Never starts analysis (FR-025)."""
        body = self._read_json_body()
        prompt = body.get("prompt", "").strip()
        triggers_raw = body.get("triggers", "").strip()
        if prompt:
            app_state.set_prompt(prompt)
            log.info("Prompt changed: %s", prompt[:80])
        keywords = [k.strip().lower() for k in triggers_raw.split(",") if k.strip()]
        app_state.set_triggers(keywords)
        if keywords:
            log.info("Trigger keywords: %s", keywords)
        persist_settings()
        self._send_json({"ok": bool(prompt)})

    def _handle_start(self):
        """Start or restart the analysis pipeline (FR-024). Idempotent."""
        app_state.set_analysis_active(True)
        persist_settings()
        started = False
        if _start_analysis_callback is not None:
            started = _start_analysis_callback()
        # @claude started=False while the VLM is still loading is fine: main
        # @claude starts the pipeline once loading completes (analysis_active).
        self._send_json({"ok": True, "started": started})

    def _handle_vlm_switch(self):
        """
        Request:  {"model": "<model_id>"}
        Response: {"ok": bool, "reason": str}
        The switch is performed by the inference worker between inferences.
        """
        from holder import request_switch
        body = self._read_json_body()
        name = (body.get("model") or "").strip()
        if not name:
            self._send_json({"ok": False, "reason": "model required"}, status=400)
            return
        ok, reason = request_switch(name)
        self._send_json({"ok": ok, "reason": reason}, status=200 if ok else 400)


# ── Server bootstrap ─────────────────────────────────────────────────────────

def start_server(port: int = 8300):
    server = ThreadingHTTPServer(("0.0.0.0", port), AnalyzerHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

"""
Babycat analyzer — internal HTTP server.

Internal only: the container publishes no port; the router is the sole
HTTP caller (SDD §6.3). No authentication — requests that reach here
already passed the router.

Endpoints:
  GET  /events      SSE (inference results + pipeline/VLM state)
  GET  /stream      MJPEG stream (VLM input frames)
  POST /prompt      Change VLM prompt / trigger keywords
  POST /presets     Change label vocabulary / time-ranged presets
  POST /start       Start or restart analysis (FR-024)
  POST /stop        Stop analysis (FR-049, FR-051)
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
_stop_analysis_callback: Callable[[], None] | None = None

MAX_BODY = 65536  # @claude 64KB cap on request bodies.


def set_start_analysis_callback(callback: Callable[[], bool]) -> None:
    """Register the analysis-start callback from the live main module."""
    global _start_analysis_callback
    _start_analysis_callback = callback


def set_stop_analysis_callback(callback: Callable[[], None]) -> None:
    """Register the analysis-stop callback from the live main module."""
    global _stop_analysis_callback
    _stop_analysis_callback = callback


def snapshot_sse_message() -> bytes:
    try:
        snap = app_state.snapshot()
    except Exception:
        log.exception("SSE snapshot failed")
        return b": snapshot_unavailable\n\n"
    return f"data: {json.dumps(snap, ensure_ascii=False)}\n\n".encode()


def persist_settings() -> None:
    settings.save(
        app_state.get_prompt(), app_state.get_triggers(),
        app_state.get_label_groups(), app_state.get_presets(),
        app_state.is_analysis_active(),
    )


class AnalyzerHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # @claude No per-request access log here: the router is the only
        # @claude caller and keeps the access log (SDD §8.4); the SSE and MJPEG
        # @claude connections would otherwise log continuously.
        pass

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/stream":
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
        elif path == "/presets":
            self._handle_presets()
        elif path == "/start":
            self._handle_start()
        elif path == "/stop":
            self._handle_stop()
        elif path == "/vlm/switch":
            self._handle_vlm_switch()
        else:
            self.send_error(404)

    # ── Utilities ────────────────────────────────────────────────────────────

    def _read_json_body(self) -> dict | None:
        """Parse the JSON object body. Returns None after answering 400 when
        the body is missing, oversized, or not a JSON object (SDD §6.5)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            length = 0
        if length <= 0:
            self._send_json({"detail": "request body required"}, status=400)
            return None
        if length > MAX_BODY:
            self._send_json({"detail": "request body too large"}, status=400)
            return None
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except ValueError:
            self._send_json({"detail": "invalid request body"}, status=400)
            return None
        if not isinstance(body, dict):
            self._send_json({"detail": "invalid request body"}, status=400)
            return None
        return body

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
        """Store the prompt and keywords. Never starts analysis (FR-025).
        Validation precedes any state change, so a rejected request leaves
        both values untouched — no partial apply."""
        body = self._read_json_body()
        if body is None:
            return
        prompt = str(body.get("prompt", "")).strip()
        triggers_raw = str(body.get("triggers", "")).strip()
        if not prompt:
            self._send_json({"detail": "prompt required"}, status=400)
            return
        keywords = [k.strip().lower() for k in triggers_raw.split(",") if k.strip()]
        app_state.set_prompt(prompt)
        log.info("Prompt changed: %s", prompt[:80])
        app_state.set_triggers(keywords)
        if keywords:
            log.info("Trigger keywords: %s", keywords)
        persist_settings()
        self._send_json({"ok": True})

    def _handle_presets(self):
        """
        Store the label vocabulary and time-ranged presets (2층).
        Request: {"labels": {"<label>": ["<synonym>", ...], ...},
                  "presets": [{"id", "start", "end", "prompt"?, "labels"?}, ...]}
        Both are opaque client-injected data; validation only checks shape
        and time format, and malformed entries are dropped (settings.py).
        Omitted keys leave the stored value untouched.
        """
        body = self._read_json_body()
        if body is None:
            return
        if "labels" not in body and "presets" not in body:
            self._send_json({"detail": "labels or presets required"}, status=400)
            return
        # @claude Validate everything before applying anything — a rejected
        # @claude request leaves both values untouched (no partial apply),
        # @claude same rule as /prompt.
        labels = presets = None
        if "labels" in body:
            labels = settings.validate_labels(body["labels"])
            if labels is None:
                self._send_json({"detail": "malformed labels"}, status=400)
                return
        if "presets" in body:
            presets = settings.validate_presets(body["presets"])
            if presets is None:
                self._send_json({"detail": "malformed presets"}, status=400)
                return
        if labels is not None:
            app_state.set_label_groups(labels)
            log.info("Label groups changed: %s", list(labels))
        if presets is not None:
            app_state.set_presets(presets)
            log.info("Presets changed: %s", [p["id"] for p in presets])
        persist_settings()
        self._send_json({"ok": True,
                         "labels": app_state.get_label_groups(),
                         "presets": app_state.get_presets()})

    def _handle_start(self):
        """Start or restart the analysis pipeline (FR-024). Idempotent."""
        app_state.set_analysis_active(True)
        persist_settings()
        started = False
        if _start_analysis_callback is not None:
            try:
                started = _start_analysis_callback()
            except Exception as e:
                # @claude A pipeline that cannot be built (e.g. a missing GStreamer
                # @claude element on the host) must surface as a 500 with the
                # @claude cause, not as a dropped connection: the router relays
                # @claude the status and the client shows the detail (SDD §6.5).
                # @claude The active flag stays set so a later start can retry.
                log.error("analysis start failed: %s", e)
                self._send_json({"detail": f"pipeline start failed: {e}"}, status=500)
                return
        # @claude started=False while the VLM is still loading: the active flag
        # @claude is recorded and main starts the pipeline once loading completes.
        self._send_json({"ok": True, "started": started})

    def _handle_stop(self):
        """Stop the analysis pipeline (FR-049, FR-051). Idempotent. The active
        flag is dropped first so nothing restarts the pipeline afterwards."""
        app_state.set_analysis_active(False)
        persist_settings()
        if _stop_analysis_callback is not None:
            _stop_analysis_callback()
        self._send_json({"ok": True})

    def _handle_vlm_switch(self):
        """
        Request:  {"model": "<model_id>"}
        Response: 200 {"ok": true} when queued; 400 {"detail": reason} when
        refused. The switch is performed by the inference worker between
        inferences.
        """
        from holder import request_switch
        body = self._read_json_body()
        if body is None:
            return
        name = str(body.get("model") or "").strip()
        if not name:
            self._send_json({"detail": "model required"}, status=400)
            return
        ok, reason = request_switch(name)
        if ok:
            self._send_json({"ok": True})
        else:
            self._send_json({"detail": reason}, status=400)


# ── Server bootstrap ─────────────────────────────────────────────────────────

def start_server(port: int = 8080):
    server = ThreadingHTTPServer(("0.0.0.0", port), AnalyzerHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

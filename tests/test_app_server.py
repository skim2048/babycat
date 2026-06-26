import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import server as server_module  # noqa: E402


class ImmediateThread:
    def __init__(self, target=None, args=(), daemon=None):
        self._target = target
        self._args = args

    def start(self):
        if self._target is not None:
            self._target(*self._args)


def test_camera_restart_uses_registered_callback(monkeypatch):
    calls = []

    monkeypatch.setattr(server_module.threading, "Thread", ImmediateThread)
    server_module.set_restart_pipeline_callback(lambda reason: calls.append(reason) or True)

    handler = server_module.AppHandler.__new__(server_module.AppHandler)
    handler._schedule_camera_restart()

    assert calls == ["camera_apply"]


def test_app_cors_allows_webview_origin(monkeypatch):
    sent = []

    monkeypatch.delenv("CORS_EXTRA_ORIGINS", raising=False)
    handler = server_module.AppHandler.__new__(server_module.AppHandler)
    handler.headers = {"Origin": "http://localhost"}
    handler.send_header = lambda name, value: sent.append((name, value))

    handler._send_cors_headers()

    assert ("Access-Control-Allow-Origin", "http://localhost") in sent
    assert ("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE") in sent
    assert ("Access-Control-Allow-Headers", "Authorization, Content-Type, Range") in sent


def test_app_cors_allows_extra_origin(monkeypatch):
    monkeypatch.setenv("CORS_EXTRA_ORIGINS", "https://example.com")

    assert server_module.allowed_cors_origin("https://example.com") == "https://example.com"


def test_app_options_preflight_returns_no_content():
    responses = []
    sent = []
    ended = []

    handler = server_module.AppHandler.__new__(server_module.AppHandler)
    handler.send_response = lambda code: responses.append(code)
    handler.send_header = lambda name, value: sent.append((name, value))
    handler.end_headers = lambda: ended.append(True)

    handler.do_OPTIONS()

    assert responses == [204]
    assert ("Content-Length", "0") in sent
    assert ended == [True]


def test_snapshot_sse_message_returns_comment_when_snapshot_fails(monkeypatch):
    class BrokenState:
        def snapshot(self):
            raise RuntimeError("snapshot unavailable")

    monkeypatch.setattr(server_module, "app_state", BrokenState())

    assert server_module.snapshot_sse_message() == b": snapshot_unavailable\n\n"

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import ptz as ptz_module  # noqa: E402


def test_issue_request_returns_none_when_ptz_is_not_configured(monkeypatch):
    monkeypatch.setattr(ptz_module, "is_configured", lambda: False)
    calls = []
    monkeypatch.setattr(ptz_module, "_post", lambda body: calls.append(body) or "<ok/>")

    result = ptz_module._issue_request("<body/>", "move")

    assert result is None
    assert calls == []


def test_poll_once_updates_current_position(monkeypatch):
    monkeypatch.setattr(ptz_module, "get_status", lambda: {"pan": 0.123, "tilt": -0.456})

    with ptz_module._lock:
        ptz_module._current = {"pan": None, "tilt": None}

    ptz_module.poll_once()

    assert ptz_module.get_current() == {"pan": 0.123, "tilt": -0.456}


def test_get_status_parses_pan_tilt_values(monkeypatch):
    xml = '<PanTilt x="0.100" y="-0.200"/>'
    monkeypatch.setattr(ptz_module, "_issue_request", lambda body, operation: xml)

    status = ptz_module.get_status()

    assert status == {"pan": 0.1, "tilt": -0.2}

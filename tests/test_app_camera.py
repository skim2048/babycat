import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import camera as camera_module  # noqa: E402


def test_apply_mediamtx_source_builds_rtsp_url_before_update(monkeypatch):
    captured = {}

    def fake_update(rtsp_url):
        captured["rtsp_url"] = rtsp_url
        return True

    monkeypatch.setattr(camera_module, "_update_mediamtx", fake_update)

    ok = camera_module._apply_mediamtx_source({
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "pa ss",
        "rtsp_port": 8554,
        "stream_path": "live/main",
    })

    assert ok is True
    assert captured["rtsp_url"] == "rtsp://admin:pa%20ss@192.168.0.10:8554/live/main"


def test_startup_apply_uses_shared_mediamtx_apply_helper(monkeypatch):
    calls = []

    monkeypatch.setattr(camera_module, "load", lambda: {
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "onvif_port": 2020,
    })
    monkeypatch.setattr(camera_module.ptz, "configure", lambda *args: None)
    monkeypatch.setattr(camera_module, "_apply_mediamtx_source", lambda config: calls.append(config.copy()) or True)
    monkeypatch.setattr(camera_module.camera_ready, "set", lambda: calls.append("ready"))

    camera_module.startup_apply()

    assert calls[0]["ip"] == "192.168.0.10"
    assert calls[0]["password"] == "secret"
    assert calls[1] == "ready"


def test_configure_ptz_builds_onvif_url_from_config(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        camera_module.ptz,
        "configure",
        lambda onvif_url, username, password: captured.update({
            "onvif_url": onvif_url,
            "username": username,
            "password": password,
        }),
    )

    camera_module._configure_ptz({
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "onvif_port": 8899,
    })

    assert captured == {
        "onvif_url": "http://192.168.0.10:8899/onvif/service",
        "username": "admin",
        "password": "secret",
    }

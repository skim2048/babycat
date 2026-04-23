import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import camera as camera_module  # noqa: E402


def test_profile_view_masks_password_and_marks_configured(monkeypatch):
    monkeypatch.setattr(camera_module, "load", lambda: {
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "stream_path": "stream1",
    })

    result = camera_module.profile_view()

    assert result["configured"] is True
    assert result["source_type"] == "rtsp_camera"
    assert result["password_set"] is True
    assert result["ip"] == "192.168.0.10"
    assert "password" not in result


def test_profile_view_returns_unconfigured_for_unsupported_source_type(monkeypatch):
    monkeypatch.setattr(camera_module, "load", lambda: {
        "source_type": "local_video",
        "path": "/tmp/demo.mp4",
    })

    result = camera_module.profile_view()

    assert result == {
        "configured": False,
        "source_type": "local_video",
    }


def test_normalize_profile_defaults_to_rtsp_camera_and_keeps_onvif_optional():
    normalized, error = camera_module._normalize_profile({
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
    }, {})

    assert error is None
    assert normalized == {
        "source_type": "rtsp_camera",
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "rtsp_port": 554,
        "onvif_port": None,
        "stream_path": "stream1",
        "stream_protocol": "hls",
    }


def test_normalize_profile_preserves_saved_password_and_allows_onvif_clear():
    normalized, error = camera_module._normalize_profile({
        "ip": "192.168.0.11",
        "username": "admin2",
        "password": None,
        "onvif_port": None,
    }, {
        "source_type": "rtsp_camera",
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "onvif_port": 2020,
    })

    assert error is None
    assert normalized["password"] == "secret"
    assert normalized["onvif_port"] is None
    assert normalized["ip"] == "192.168.0.11"
    assert normalized["username"] == "admin2"


def test_normalize_profile_coerces_unknown_stream_protocol_to_hls():
    normalized, error = camera_module._normalize_profile({
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "stream_protocol": "rtsp",
    }, {})

    assert error is None
    assert normalized["stream_protocol"] == "hls"


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


def test_startup_apply_uses_shared_runtime_activation_helper(monkeypatch):
    calls = []

    monkeypatch.setattr(camera_module, "load", lambda: {
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "onvif_port": 2020,
    })
    monkeypatch.setattr(camera_module.ptz, "configure", lambda *args: None)
    monkeypatch.setattr(
        camera_module,
        "_activate_runtime",
        lambda config, configure_ptz=True: calls.append((config.copy(), configure_ptz)) or True,
    )

    camera_module.startup_apply()

    assert len(calls) == 1
    config, configure_ptz = calls[0]
    assert configure_ptz is False
    assert config["source_type"] == "rtsp_camera"
    assert config["ip"] == "192.168.0.10"
    assert config["username"] == "admin"
    assert config["password"] == "secret"
    assert config["onvif_port"] == 2020
    assert config["rtsp_port"] == 554


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


def test_configure_ptz_clears_ptz_when_onvif_is_missing(monkeypatch):
    calls = []

    monkeypatch.setattr(camera_module.ptz, "clear_config", lambda: calls.append("cleared"))
    monkeypatch.setattr(camera_module.ptz, "configure", lambda *args: calls.append("configured"))

    camera_module._configure_ptz({
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
        "onvif_port": None,
    })

    assert calls == ["cleared"]


def test_activate_runtime_configures_ptz_then_marks_camera_ready(monkeypatch):
    calls = []

    monkeypatch.setattr(camera_module, "_configure_ptz", lambda config: calls.append(("ptz", config["ip"])))
    monkeypatch.setattr(camera_module, "_apply_mediamtx_source", lambda config: calls.append(("mediamtx", config["ip"])) or True)
    monkeypatch.setattr(camera_module.camera_ready, "set", lambda: calls.append(("ready", None)))

    ok = camera_module._activate_runtime({
        "ip": "192.168.0.10",
        "username": "admin",
        "password": "secret",
    })

    assert ok is True
    assert calls == [("ptz", "192.168.0.10"), ("mediamtx", "192.168.0.10"), ("ready", None)]


def test_activate_runtime_rejects_unsupported_source_type():
    ok = camera_module._activate_runtime({
        "source_type": "local_video",
    })

    assert ok is False

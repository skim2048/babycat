"""Babycat API/auth lower-level tests.

These tests avoid HTTP client integration because the local ASGI test
stack can block in this environment. We still validate the security- and
data-path behavior directly.

@chatgpt
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _tmp_db.name
_tmp_db.close()

_tmp_clip_dir = tempfile.mkdtemp()
os.environ["CAM_DIR"] = _tmp_clip_dir

import sys  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import auth as auth_module  # noqa: E402
import app_proxy as app_proxy_module  # noqa: E402
import main as api_main  # noqa: E402
from auth import DEFAULT_PASS, DEFAULT_USER, authenticate, change_password, init_users, rotate_refresh_token, verify_token  # noqa: E402
from database import init_db  # noqa: E402
from fastapi import HTTPException  # noqa: E402


init_db()
_seed_conn = sqlite3.connect(os.environ["DB_PATH"])
_seed_conn.row_factory = sqlite3.Row
try:
    init_users(_seed_conn)
finally:
    _seed_conn.close()


def _conn():
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture(autouse=True)
def _reset_state():
    conn = _conn()
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM devices")
    conn.execute("DELETE FROM refresh_tokens")
    salt = "test-salt"
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ?, password_changed = 0 WHERE username = ?",
        (auth_module._hash_password(DEFAULT_PASS, salt), salt, DEFAULT_USER),
    )
    conn.commit()
    conn.close()

    for root, _, files in os.walk(_tmp_clip_dir, topdown=False):
        for name in files:
            os.unlink(os.path.join(root, name))

    yield


def _clip_path(name: str) -> Path:
    if len(name) >= 8 and name[:8].isdigit():
        sub = Path(_tmp_clip_dir) / name[:4] / name[4:6]
    else:
        sub = Path(_tmp_clip_dir)
    sub.mkdir(parents=True, exist_ok=True)
    return sub / name


def test_health_direct():
    assert api_main.health() == {"status": "ok"}


def test_authenticate_without_remember_me_still_has_refresh_token():
    conn = _conn()
    try:
        result = authenticate(DEFAULT_USER, DEFAULT_PASS, conn, remember_me=False)
        assert result is not None
        assert result["refresh_token"] is not None
        assert verify_token(result["token"]) is not None
    finally:
        conn.close()


def test_refresh_token_rotation_is_single_use():
    conn = _conn()
    try:
        result = authenticate(DEFAULT_USER, DEFAULT_PASS, conn, remember_me=True)
        assert result is not None
        old_refresh = result["refresh_token"]

        rotated = rotate_refresh_token(old_refresh, conn)
        assert rotated is not None
        username, new_refresh = rotated
        assert username == DEFAULT_USER
        assert new_refresh != old_refresh

        assert rotate_refresh_token(old_refresh, conn) is None
    finally:
        conn.close()


def test_change_password_revokes_existing_refresh_tokens():
    conn = _conn()
    try:
        result = authenticate(DEFAULT_USER, DEFAULT_PASS, conn, remember_me=True)
        assert result is not None
        refresh_token = result["refresh_token"]

        assert change_password(DEFAULT_USER, DEFAULT_PASS, "admin2", conn) is True
        assert rotate_refresh_token(refresh_token, conn) is None

        relogin = authenticate(DEFAULT_USER, "admin2", conn, remember_me=False)
        assert relogin is not None
    finally:
        conn.close()


def test_get_camera_masks_password(monkeypatch):
    class DummyRequest:
        headers = {"Authorization": "Bearer token"}

    def fake_proxy(method, path, auth_header, body=None, timeout=10):
        return 200, {
            "configured": True,
            "source_type": "rtsp_camera",
            "ip": "192.168.0.10",
            "username": "admin",
            "password": "secret",
            "stream_path": "stream1",
        }

    monkeypatch.setattr(api_main, "proxy_app", lambda app_internal_url, method, path, auth_header, body=None, timeout=10: fake_proxy(method, path, auth_header, body, timeout))
    result = api_main.get_camera(DummyRequest(), _={})
    assert result.configured is True
    assert result.source_type == "rtsp_camera"
    assert result.password_set is True
    assert not hasattr(result, "password")


def test_camera_profile_out_preserves_upstream_password_set_and_ptz_home():
    result = app_proxy_module.camera_profile_out({
        "configured": True,
        "source_type": "rtsp_camera",
        "ip": "192.168.0.10",
        "username": "admin",
        "password_set": True,
        "ptz_home": {"pan": 0.22, "tilt": -0.553},
    })

    assert result.password_set is True
    assert result.ptz_home is not None
    assert result.ptz_home.pan == 0.22
    assert result.ptz_home.tilt == -0.553


def test_camera_profile_out_returns_unconfigured_when_upstream_is_empty():
    result = app_proxy_module.camera_profile_out(None)
    assert result.configured is False


def test_set_camera_maps_upstream_server_error_to_502(monkeypatch):
    class DummyRequest:
        headers = {"Authorization": "Bearer token"}

    class DummyBody:
        def model_dump(self):
            return {"source_type": "rtsp_camera", "ip": "192.168.0.10", "username": "admin", "onvif_port": None}

    def fake_proxy(method, path, auth_header, body=None, timeout=10):
        return 500, {"ok": False, "error": "boom"}

    monkeypatch.setattr(api_main, "proxy_app", lambda app_internal_url, method, path, auth_header, body=None, timeout=10: fake_proxy(method, path, auth_header, body, timeout))
    with pytest.raises(HTTPException) as exc:
        api_main.set_camera(DummyRequest(), DummyBody(), _={})
    assert exc.value.status_code == 502


def test_list_clips_filters_small_files_and_reads_metadata():
    clip = _clip_path("20260416_101234_567.mp4")
    clip.write_bytes(b"\x00" * 20480)
    clip.with_suffix(".json").write_text(
        '{"timestamp": 123, "keywords": ["person"], "vlm_text": "standing"}',
        encoding="utf-8",
    )
    small = _clip_path("20260416_101300_000.mp4")
    small.write_bytes(b"\x00" * 5000)

    clips = api_main._list_clips()
    assert len(clips) == 1
    assert clips[0].name == clip.name
    assert clips[0].timestamp == 123
    assert clips[0].keywords == ["person"]
    assert clips[0].vlm_text == "standing"


def test_list_clips_excludes_pending_or_invalid_metadata():
    pending = _clip_path("20260416_101234_567.mp4")
    pending.write_bytes(b"\x00" * 20480)

    broken = _clip_path("20260416_101235_000.mp4")
    broken.write_bytes(b"\x00" * 20480)
    broken.with_suffix(".json").write_text("{", encoding="utf-8")

    clips = api_main._list_clips()

    assert clips == []


def test_list_clips_q_filters_by_vlm_text_only():
    first = _clip_path("20260416_101234_567.mp4")
    first.write_bytes(b"\x00" * 20480)
    first.with_suffix(".json").write_text(
        '{"timestamp": 123, "keywords": ["writing"], "vlm_text": "A person is writing on paper."}',
        encoding="utf-8",
    )

    second = _clip_path("writing_in_filename_only.mp4")
    second.write_bytes(b"\x00" * 20480)
    second.with_suffix(".json").write_text(
        '{"timestamp": 124, "keywords": ["person"], "vlm_text": "A person is standing still."}',
        encoding="utf-8",
    )

    clips = api_main._list_clips("writing")

    assert [clip.name for clip in clips] == [first.name]


def test_resolve_clip_prefers_year_month_path():
    clip = _clip_path("20260416_101234_567.mp4")
    clip.write_bytes(b"\x00" * 20480)
    resolved = api_main._resolve_clip(clip.name)
    assert resolved == clip


def test_resolve_clip_rejects_path_traversal():
    with pytest.raises(HTTPException) as exc:
        api_main._resolve_clip("../secret.mp4")
    assert exc.value.status_code == 400

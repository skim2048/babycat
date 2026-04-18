"""Babycat API server — unit tests.

Exercises every endpoint via FastAPI TestClient. Runs without GStreamer
or a loaded VLM.

@claude
"""

import os
import tempfile

import pytest

# @claude Redirect DB and clip directory to temp paths; must be set before importing api/main.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _tmp_db.name
_tmp_db.close()

_tmp_clip_dir = tempfile.mkdtemp()
os.environ["CAM_DIR"] = _tmp_clip_dir

# @claude Make the api/ directory importable.
import sys  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from fastapi.testclient import TestClient  # noqa: E402

from auth import DEFAULT_USER, create_token, init_users  # noqa: E402
from database import init_db  # noqa: E402
from main import app  # noqa: E402

import sqlite3 as _sqlite3  # noqa: E402

# @claude lifespan only runs when entering the TestClient context, so seed tables
# @claude and the default user at module import time.
init_db()
_seed_conn = _sqlite3.connect(os.environ["DB_PATH"])
_seed_conn.row_factory = _sqlite3.Row
try:
    init_users(_seed_conn)
finally:
    _seed_conn.close()

# @claude Auto-inject a valid token on every request (issued directly, bypassing lifespan).
_token = create_token(DEFAULT_USER)
client = TestClient(app, headers={"Authorization": f"Bearer {_token}"})


# ── Helpers ─────────────────────────────────────────────────────────────────

def _clip_path(name: str) -> str:
    """Build _tmp/YYYY/MM/{name} from the leading YYYYMMDD of `name`;
    fall back to the base directory (exercises the rglob fallback path).

    @claude
    """
    if len(name) >= 8 and name[:8].isdigit():
        sub = os.path.join(_tmp_clip_dir, name[:4], name[4:6])
    else:
        sub = _tmp_clip_dir
    os.makedirs(sub, exist_ok=True)
    return os.path.join(sub, name)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_db():
    """Reset DB rows before each test. @claude"""
    conn = _sqlite3.connect(os.environ["DB_PATH"])
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM devices")
    conn.commit()
    conn.close()
    yield


@pytest.fixture(autouse=True)
def _clean_clips():
    """Empty the temp clip directory before each test. @claude"""
    for root, _, files in os.walk(_tmp_clip_dir, topdown=False):
        for f in files:
            os.unlink(os.path.join(root, f))
    yield


@pytest.fixture
def clip_file():
    """20KB valid clip stored under the year/month tree. @claude"""
    name = "20260416_101234_567.mp4"
    path = _clip_path(name)
    with open(path, "wb") as f:
        f.write(b"\x00" * 20480)
    return name


@pytest.fixture
def small_clip():
    """Incomplete clip under 10KB (should be filtered out). @claude"""
    name = "20260416_101300_000.mp4"
    path = _clip_path(name)
    with open(path, "wb") as f:
        f.write(b"\x00" * 5000)
    return name


# ── Health ───────────────────────────────────────────────────────────────────


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── Clips ────────────────────────────────────────────────────────────────────


def test_list_clips_empty():
    r = client.get("/clips")
    assert r.status_code == 200
    data = r.json()
    assert data["clips"] == []
    assert data["total"] == 0


def test_list_clips_with_file(clip_file):
    r = client.get("/clips")
    data = r.json()
    assert data["total"] == 1
    assert data["clips"][0]["name"] == clip_file
    assert data["clips"][0]["size"] == 20480


def test_list_clips_filters_small(clip_file, small_clip):
    r = client.get("/clips")
    data = r.json()
    names = [c["name"] for c in data["clips"]]
    assert clip_file in names
    assert small_clip not in names


def test_list_clips_search(clip_file):
    r = client.get(f"/clips?q={clip_file[:8]}")
    assert r.json()["total"] == 1
    r = client.get("/clips?q=nonexistent")
    assert r.json()["total"] == 0


def test_list_clips_pagination(clip_file):
    r = client.get("/clips?limit=1&offset=0")
    assert len(r.json()["clips"]) == 1
    r = client.get("/clips?limit=1&offset=1")
    assert len(r.json()["clips"]) == 0


def test_get_clip(clip_file):
    r = client.get(f"/clips/{clip_file}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"


def test_get_clip_range(clip_file):
    r = client.get(f"/clips/{clip_file}", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert len(r.content) == 100
    assert "content-range" in r.headers


def test_get_clip_not_found():
    r = client.get("/clips/nonexistent.mp4")
    assert r.status_code == 404


def test_get_clip_path_traversal():
    # @claude FastAPI treats %2F as a path separator -> route mismatch -> 404;
    # @claude names containing `..` return 400. Either way the file is unreachable.
    r = client.get("/clips/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)
    # @claude Case where `..` reaches the handler as part of `name`.
    r = client.get("/clips/..passwd")
    assert r.status_code in (400, 404)


def test_delete_clips(clip_file):
    r = client.request("DELETE", "/clips", json={"names": [clip_file]})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    # @claude Confirm the file is actually gone.
    r = client.get("/clips")
    assert r.json()["total"] == 0


def test_delete_clips_empty_names():
    r = client.request("DELETE", "/clips", json={"names": []})
    assert r.status_code == 200
    assert r.json()["deleted"] == 0


def test_delete_all_clips(clip_file):
    r = client.request("DELETE", "/clips/all")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1


# ── Events ───────────────────────────────────────────────────────────────────


def test_create_event():
    r = client.post("/events", json={"trigger": "person", "clip_name": "clip.mp4"})
    assert r.status_code == 201
    data = r.json()
    assert data["id"] == 1
    assert data["trigger"] == "person"
    assert data["clip_name"] == "clip.mp4"
    assert "created_at" in data


def test_create_event_no_clip():
    r = client.post("/events", json={"trigger": "motion"})
    assert r.status_code == 201
    assert r.json()["clip_name"] is None


def test_list_events():
    client.post("/events", json={"trigger": "a"})
    client.post("/events", json={"trigger": "b"})
    r = client.get("/events")
    data = r.json()
    assert data["total"] == 2
    # @claude Newest first (id DESC).
    assert data["events"][0]["trigger"] == "b"


def test_list_events_pagination():
    for i in range(5):
        client.post("/events", json={"trigger": f"e{i}"})
    r = client.get("/events?limit=2&offset=0")
    assert len(r.json()["events"]) == 2
    r = client.get("/events?limit=2&offset=4")
    assert len(r.json()["events"]) == 1


def test_delete_events():
    client.post("/events", json={"trigger": "a"})
    client.post("/events", json={"trigger": "b"})
    r = client.request("DELETE", "/events")
    assert r.json()["deleted"] == 2
    r = client.get("/events")
    assert r.json()["total"] == 0


# ── Devices ──────────────────────────────────────────────────────────────────


def test_register_device():
    r = client.post("/devices", json={"fcm_token": "tok1", "label": "phone"})
    assert r.status_code == 200
    data = r.json()
    assert data["fcm_token"] == "tok1"
    assert data["label"] == "phone"
    assert "registered_at" in data


def test_register_device_upsert():
    client.post("/devices", json={"fcm_token": "tok1", "label": "old"})
    r = client.post("/devices", json={"fcm_token": "tok1", "label": "new"})
    assert r.json()["label"] == "new"
    # @claude Still only one row.
    r = client.get("/devices")
    assert len(r.json()["devices"]) == 1


def test_list_devices():
    client.post("/devices", json={"fcm_token": "a"})
    client.post("/devices", json={"fcm_token": "b"})
    r = client.get("/devices")
    assert len(r.json()["devices"]) == 2


def test_delete_device():
    r = client.post("/devices", json={"fcm_token": "tok1"})
    device_id = r.json()["id"]
    r = client.request("DELETE", f"/devices/{device_id}")
    assert r.json()["deleted"] == 1
    # @claude Verify the list is empty after deletion.
    r = client.get("/devices")
    assert len(r.json()["devices"]) == 0


def test_delete_device_not_found():
    r = client.request("DELETE", "/devices/999")
    assert r.status_code == 404

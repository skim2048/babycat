"""Babycat API Server — unit tests.

FastAPI TestClient로 모든 엔드포인트를 검증한다.
GStreamer/VLM 없이 실행 가능.
"""

import os
import tempfile

import pytest

# DB와 클립 디렉토리를 임시 경로로 지정 (api/main import 전에 설정해야 함)
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _tmp_db.name
_tmp_db.close()

_tmp_clip_dir = tempfile.mkdtemp()
os.environ["CAM_DIR"] = _tmp_clip_dir

# api/ 디렉토리를 import 경로에 추가
import sys  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from fastapi.testclient import TestClient  # noqa: E402

from auth import DEFAULT_USER, create_token, init_users  # noqa: E402
from database import init_db  # noqa: E402
from main import app  # noqa: E402

import sqlite3 as _sqlite3  # noqa: E402

# 테스트 시작 전 테이블 + 기본 사용자 초기화 (lifespan은 TestClient context 진입 시에만
# 실행되므로 모듈 단위에서 직접 호출한다)
init_db()
_seed_conn = _sqlite3.connect(os.environ["DB_PATH"])
_seed_conn.row_factory = _sqlite3.Row
try:
    init_users(_seed_conn)
finally:
    _seed_conn.close()

# 모든 요청에 토큰을 자동 주입 (lifespan 안 돌리고도 유효한 토큰을 직접 발급)
_token = create_token(DEFAULT_USER)
client = TestClient(app, headers={"Authorization": f"Bearer {_token}"})


# ── Helpers ─────────────────────────────────────────────────────────────────

def _clip_path(name: str) -> str:
    """파일명에서 YYYYMMDD를 추출해 _tmp/YYYY/MM/{name} 경로를 만든다.
    YYYYMMDD가 아니면 base 직하에 둔다 (rglob 폴백 검증용)."""
    if len(name) >= 8 and name[:8].isdigit():
        sub = os.path.join(_tmp_clip_dir, name[:4], name[4:6])
    else:
        sub = _tmp_clip_dir
    os.makedirs(sub, exist_ok=True)
    return os.path.join(sub, name)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_db():
    """각 테스트 전 DB 데이터 초기화."""
    conn = _sqlite3.connect(os.environ["DB_PATH"])
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM devices")
    conn.commit()
    conn.close()
    yield


@pytest.fixture(autouse=True)
def _clean_clips():
    """각 테스트 전 임시 클립 디렉토리 비우기."""
    for root, _, files in os.walk(_tmp_clip_dir, topdown=False):
        for f in files:
            os.unlink(os.path.join(root, f))
    yield


@pytest.fixture
def clip_file():
    """20KB 정상 클립 (연/월 트리에 저장)."""
    name = "20260416_101234_567.mp4"
    path = _clip_path(name)
    with open(path, "wb") as f:
        f.write(b"\x00" * 20480)
    return name


@pytest.fixture
def small_clip():
    """10KB 미만 불완전 클립 (필터링 대상)."""
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
    # FastAPI가 %2F를 경로 구분자로 처리 → 라우트 불일치 404
    # 또는 name에 .. 포함 → 400. 어느 쪽이든 파일 접근 불가
    r = client.get("/clips/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)
    # 직접 .. 이 name에 도달하는 경우
    r = client.get("/clips/..passwd")
    assert r.status_code in (400, 404)


def test_delete_clips(clip_file):
    r = client.request("DELETE", "/clips", json={"names": [clip_file]})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    # 파일이 실제로 삭제되었는지 확인
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
    # 최신순 (id DESC)
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
    # 여전히 1개만 존재
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
    # 삭제 후 목록 확인
    r = client.get("/devices")
    assert len(r.json()["devices"]) == 0


def test_delete_device_not_found():
    r = client.request("DELETE", "/devices/999")
    assert r.status_code == 404

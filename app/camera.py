"""
카메라 설정 관리 모듈

Data Management (클립 저장 아키텍처):
    각 카메라는 사용자가 지정한 고유 이름(name)으로 식별된다.
    MAC 주소나 하드웨어 ID는 사용하지 않는다.
    이름이 다르면 무조건 다른 카메라로 취급하고, 동일한 물리 장비라도
    새 이름을 부여하면 새 카메라로 간주한다.

    클립은 카메라별 디렉토리에 격리 저장된다:
        {CAM_BASE_DIR}/{camera_name}/*.mp4
        예: /data/cam/mycam/20260401_143025_baby.mp4

    카메라를 교체(새 이름으로 등록)하면 새 디렉토리가 생성되고,
    이전 카메라의 디렉토리와 클립은 그대로 보존된다.
    이전 카메라의 클립은 API를 통해 언제든 조회/다운로드 가능하다.
    자동 삭제는 절대 수행하지 않는다.
"""

import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

import ptz

log = logging.getLogger(__name__)

CONFIG_PATH = os.getenv("CONFIG_PATH", "/config/cam_profile.json")
MEDIAMTX_API = "http://babycat-mediamtx:9997"
MEDIAMTX_PATH_NAME = "live"

# 카메라별 클립 저장 베이스 디렉토리.
# 각 카메라의 클립은 {CAM_BASE_DIR}/{camera_name}/ 하위에 저장된다.
CAM_BASE_DIR = os.getenv("CAM_BASE_DIR", "/data/cam")

camera_ready = threading.Event()

_REQUIRED_FIELDS = ("name", "ip", "username", "password")
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def _validate_name(name: str) -> bool:
    """카메라 이름 검증. 1-32자, [a-zA-Z0-9_-]만 허용 (파일시스템 안전)."""
    return bool(_NAME_RE.match(name))


def get_clip_dir(config: dict) -> str:
    """카메라 설정에서 클립 저장 디렉토리 경로를 반환."""
    return os.path.join(CAM_BASE_DIR, config["name"])


def load() -> Optional[dict]:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(config: dict) -> None:
    """저장 시 기존 파일의 필드를 보존한 뒤 덮어쓴다 (ptz_home 등)."""
    existing = load() or {}
    existing.update(config)
    with open(CONFIG_PATH, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def apply(config: dict) -> dict:
    """
    카메라 설정 적용.

    name 필드가 클립 저장 디렉토리의 경계가 된다.
    성공 시 {"ok": True, "clip_dir": "/data/cam/{name}"} 반환.
    호출자는 clip_dir을 사용하여 state의 클립 디렉토리를 갱신해야 한다.
    """
    for field in _REQUIRED_FIELDS:
        if not config.get(field, "").strip():
            return {"ok": False, "error": f"'{field}' is required"}

    if not _validate_name(config["name"]):
        return {"ok": False, "error": "name must be 1-32 chars of [a-zA-Z0-9_-]"}

    config.setdefault("onvif_port", 2020)
    config.setdefault("rtsp_port", 554)
    config.setdefault("stream_path", "stream1")

    save(config)

    # PTZ 설정
    onvif_url = _build_onvif_url(config)
    ptz.configure(onvif_url, config["username"], config["password"])

    # MediaMTX RTSP 소스 설정
    rtsp_url = _build_rtsp_url(config)
    ok = _update_mediamtx(rtsp_url)
    if not ok:
        return {"ok": False, "error": "MediaMTX API connection failed"}

    clip_dir = get_clip_dir(config)
    camera_ready.set()
    return {"ok": True, "clip_dir": clip_dir}


def startup_apply() -> None:
    config = load()
    if config is None:
        log.info("No saved config — set via frontend")
        return

    # PTZ 즉시 설정
    onvif_url = _build_onvif_url(config)
    ptz.configure(onvif_url, config["username"], config["password"])

    # MediaMTX 재시도 (지수 백오프)
    rtsp_url = _build_rtsp_url(config)
    delay = 1.0
    for attempt in range(1, 11):
        if _update_mediamtx(rtsp_url):
            log.info("MediaMTX source configured (attempt %d)", attempt)
            camera_ready.set()
            return
        log.warning("MediaMTX connection failed (attempt %d/10, retry in %.0fs)", attempt, delay)
        time.sleep(delay)
        delay = min(delay * 2, 30)

    log.error("MediaMTX source config failed — 10 retries exceeded")


def _build_rtsp_url(config: dict) -> str:
    user = urllib.parse.quote(config["username"], safe="")
    pwd = urllib.parse.quote(config["password"], safe="")
    ip = config["ip"]
    port = config.get("rtsp_port", 554)
    path = config.get("stream_path", "stream1")
    return f"rtsp://{user}:{pwd}@{ip}:{port}/{path}"


def _build_onvif_url(config: dict) -> str:
    ip = config["ip"]
    port = config.get("onvif_port", 2020)
    return f"http://{ip}:{port}/onvif/service"


def _update_mediamtx(rtsp_url: str) -> bool:
    url = f"{MEDIAMTX_API}/v3/config/paths/patch/{MEDIAMTX_PATH_NAME}"
    payload = json.dumps({
        "source": rtsp_url,
        "sourceProtocol": "tcp",
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        log.error("MediaMTX API error: %s", e)
        return False

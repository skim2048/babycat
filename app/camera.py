"""
카메라 설정 관리 모듈

프론트엔드에서 입력받은 카메라 자격증명을 파일로 영속화하고,
PTZ 모듈 및 MediaMTX RTSP 소스를 런타임에 설정한다.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import ptz

CONFIG_PATH = "/app/camera.json"
MEDIAMTX_API = "http://babycat-mediamtx:9997"
MEDIAMTX_PATH_NAME = "live"

camera_ready = threading.Event()

_REQUIRED_FIELDS = ("ip", "username", "password")


def load() -> Optional[dict]:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(config: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def apply(config: dict) -> dict:
    for field in _REQUIRED_FIELDS:
        if not config.get(field, "").strip():
            return {"ok": False, "error": f"'{field}' is required"}

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
        return {"ok": False, "error": "MediaMTX API 연결 실패"}

    camera_ready.set()
    return {"ok": True}


def startup_apply() -> None:
    config = load()
    if config is None:
        print("[camera] 저장된 설정 없음 — 프론트엔드에서 설정 필요", flush=True)
        return

    # PTZ 즉시 설정
    onvif_url = _build_onvif_url(config)
    ptz.configure(onvif_url, config["username"], config["password"])

    # MediaMTX 재시도 (지수 백오프)
    rtsp_url = _build_rtsp_url(config)
    delay = 1.0
    for attempt in range(1, 11):
        if _update_mediamtx(rtsp_url):
            print(f"[camera] MediaMTX 소스 설정 완료 (시도 {attempt})", flush=True)
            camera_ready.set()
            return
        print(f"[camera] MediaMTX 연결 실패 (시도 {attempt}/10, {delay:.0f}s 후 재시도)", flush=True)
        time.sleep(delay)
        delay = min(delay * 2, 30)

    print("[camera] MediaMTX 소스 설정 실패 — 10회 재시도 초과", flush=True)


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
        print(f"[camera] MediaMTX API 오류: {e}", flush=True)
        return False

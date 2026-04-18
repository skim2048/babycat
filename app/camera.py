"""
Camera configuration module.

Babycat assumes a single camera. Clips are stored under per-year/month
directories (DATA_DIR/{YYYY}/{MM}/) and accumulate in the same location
regardless of camera-profile changes.

@claude
"""

import json
import logging
import os
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

# @claude Clip storage base directory; actual files live under {DATA_DIR}/{YYYY}/{MM}/.
DATA_DIR = os.getenv("DATA_DIR", "/data")

camera_ready = threading.Event()

_REQUIRED_FIELDS = ("ip", "username", "password")


def load() -> Optional[dict]:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(config: dict) -> None:
    """Merge into the existing file (preserving fields like ptz_home) before overwriting. @claude"""
    existing = load() or {}
    existing.update(config)
    existing.pop("name", None)  # @claude Drop a legacy field.
    with open(CONFIG_PATH, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def apply(config: dict) -> dict:
    """Apply a camera configuration. Returns {"ok": True} on success. @claude"""
    # @chatgpt Preserve the previously saved password when the user updates other
    # @chatgpt camera fields without re-entering credentials.
    existing = load() or {}
    if not config.get("password") and existing.get("password"):
        config["password"] = existing["password"]

    for field in _REQUIRED_FIELDS:
        if not config.get(field, "").strip():
            return {"ok": False, "error": f"'{field}' is required"}

    config.setdefault("onvif_port", 2020)
    config.setdefault("rtsp_port", 554)
    config.setdefault("stream_path", "stream1")

    save(config)

    onvif_url = _build_onvif_url(config)
    ptz.configure(onvif_url, config["username"], config["password"])

    rtsp_url = _build_rtsp_url(config)
    ok = _update_mediamtx(rtsp_url)
    if not ok:
        return {"ok": False, "error": "MediaMTX API connection failed"}

    camera_ready.set()
    return {"ok": True}


def startup_apply() -> None:
    config = load()
    if config is None:
        log.info("No saved config — set via frontend")
        return

    onvif_url = _build_onvif_url(config)
    ptz.configure(onvif_url, config["username"], config["password"])

    # @claude MediaMTX may not be ready yet; retry with exponential backoff.
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

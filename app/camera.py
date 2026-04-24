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

DEFAULT_SOURCE_TYPE = "rtsp_camera"
_REQUIRED_RTSP_FIELDS = ("ip", "username", "password")
_STREAM_PROTOCOLS = {"hls", "webrtc"}


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


def profile_view() -> dict:
    config = load()
    if not config:
        return {"configured": False}
    return _profile_view(config)


def apply(config: dict) -> dict:
    """Apply a camera configuration. Returns {"ok": True} on success. @claude"""
    existing = load() or {}
    normalized, error = _normalize_profile(config, existing)
    if error:
        return {"ok": False, "error": error}

    # Runtime readiness must track the currently active camera source, not the
    # last persisted profile. Clear first so failed applies do not leave a stale
    # "camera ready" state behind.
    camera_ready.clear()

    if not _activate_runtime(normalized):
        return {"ok": False, "error": "MediaMTX API connection failed"}

    save(normalized)
    return {"ok": True}


def startup_apply() -> None:
    saved = load()
    if saved is None:
        log.info("No saved config — set via frontend")
        return

    config, error = _normalize_profile(saved, saved)
    if error:
        log.error("Saved camera config is invalid: %s", error)
        return

    _configure_ptz(config)

    # @claude MediaMTX may not be ready yet; retry with exponential backoff.
    camera_ready.clear()
    delay = 1.0
    for attempt in range(1, 11):
        if _activate_runtime(config, configure_ptz=False):
            log.info("MediaMTX source configured (attempt %d)", attempt)
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
    port = config["onvif_port"]
    return f"http://{ip}:{port}/onvif/service"


def _source_type(config: dict | None, existing: dict | None = None) -> str:
    raw = None
    if config:
        raw = config.get("source_type")
    if not raw and existing:
        raw = existing.get("source_type")
    value = str(raw or DEFAULT_SOURCE_TYPE).strip()
    return value or DEFAULT_SOURCE_TYPE


def _normalize_profile(config: dict, existing: dict) -> tuple[dict | None, str | None]:
    source_type = _source_type(config, existing)
    normalizer = _source_normalizer(source_type)
    if normalizer is not None:
        return normalizer(config, existing, source_type)
    return None, f"unsupported source_type: {source_type}"


def _normalize_rtsp_camera_profile(config: dict, existing: dict, source_type: str) -> tuple[dict | None, str | None]:
    password = config.get("password")
    if not password and existing.get("password"):
        password = existing["password"]

    normalized = {
        "source_type": source_type,
        "ip": str(config.get("ip", existing.get("ip", ""))).strip(),
        "username": str(config.get("username", existing.get("username", ""))).strip(),
        "password": password,
        "rtsp_port": _coalesce(config, existing, "rtsp_port", 554),
        "onvif_port": _coalesce_optional(config, existing, "onvif_port"),
        "stream_path": str(_coalesce(config, existing, "stream_path", "stream1")).strip(),
        "stream_protocol": _normalize_stream_protocol(_coalesce(config, existing, "stream_protocol", "hls")),
    }

    for field in _REQUIRED_RTSP_FIELDS:
        value = normalized.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"'{field}' is required"

    return normalized, None


def _coalesce(config: dict, existing: dict, key: str, default):
    value = config.get(key)
    if value is not None:
        return value
    value = existing.get(key)
    if value is not None:
        return value
    return default


def _coalesce_optional(config: dict, existing: dict, key: str):
    if key in config:
        return config.get(key)
    return existing.get(key)


def _normalize_stream_protocol(value) -> str:
    protocol = str(value or "hls").strip().lower()
    if protocol not in _STREAM_PROTOCOLS:
        return "hls"
    return protocol


def _profile_view(config: dict) -> dict:
    source_type = _source_type(config)
    viewer = _source_profile_viewer(source_type)
    if viewer is None:
        return {"configured": False, "source_type": source_type}
    return viewer(config, source_type)


def _profile_view_rtsp_camera(config: dict, source_type: str) -> dict:
    return {
        "configured": True,
        "source_type": source_type,
        **{k: v for k, v in config.items() if k != "password"},
        "password_set": bool(config.get("password")),
    }


def _configure_ptz(config: dict) -> None:
    if not config.get("onvif_port"):
        ptz.clear_config()
        return
    ptz.configure(_build_onvif_url(config), config["username"], config["password"])


def _apply_mediamtx_source(config: dict) -> bool:
    return _update_mediamtx(_build_rtsp_url(config))


def _activate_runtime(config: dict, configure_ptz: bool = True) -> bool:
    activator = _source_runtime_activator(_source_type(config))
    if activator is None:
        return False
    return activator(config, configure_ptz=configure_ptz)


def _activate_rtsp_camera_runtime(config: dict, configure_ptz: bool = True) -> bool:
    if configure_ptz:
        _configure_ptz(config)
    if not _apply_mediamtx_source(config):
        return False
    camera_ready.set()
    return True


def _source_profile_viewer(source_type: str):
    if source_type == DEFAULT_SOURCE_TYPE:
        return _profile_view_rtsp_camera
    return None


def _source_normalizer(source_type: str):
    if source_type == DEFAULT_SOURCE_TYPE:
        return _normalize_rtsp_camera_profile
    return None


def _source_runtime_activator(source_type: str):
    if source_type == DEFAULT_SOURCE_TYPE:
        return _activate_rtsp_camera_runtime
    return None


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

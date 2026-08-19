"""
Video source profile management and MediaMTX source configuration.

Babycat assumes a single camera (v1.0). Two profile slots, both owned by
the streamer alone (SDD §5.1):

  - registered profile (CONFIG_PATH) — the only thing POST /profile
    touches. Registration never configures MediaMTX or PTZ (FR-048).
  - applied profile (APPLIED_PATH) — a copy of the registered profile
    promoted at streaming start, persisted with the streaming_active
    flag and the PTZ home. Connection, failure recovery, and restart
    restore always use this slot (FR-014).

The RTSP source is configured at runtime through the MediaMTX control
API on localhost — owner and consumer of the profile live in the same
container (SDD §4.2), so a restart recovers the source config through
the normal startup path with no external watchdog.

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
APPLIED_PATH = os.getenv("APPLIED_PATH", "/config/cam_applied.json")
MEDIAMTX_API = os.getenv("MEDIAMTX_API", "http://127.0.0.1:9997")
MEDIAMTX_PATH_NAME = "live"
# @claude MediaMTX's passive default: the path waits for a publisher instead of
# @claude pulling from the camera. Patching the source back to this value is how
# @claude streaming stop detaches the camera (FR-049).
MEDIAMTX_SOURCE_DETACHED = "publisher"

# @claude Serializes every read-merge-write cycle on the two profile files;
# @claude writes go through a temp file + os.replace so a crash mid-write
# @claude cannot leave a torn file behind.
_config_lock = threading.Lock()

# @claude Serializes the runtime transitions — streaming start, streaming stop,
# @claude and each restore attempt (SDD §4.2). The file lock above protects
# @claude individual writes; this one protects whole read-decide-apply-save
# @claude sequences, so a stop cannot slip between a restore attempt's slot
# @claude read and its source patch, and start/stop cannot interleave into a
# @claude flag/source mismatch. Acquisition order is always runtime → config.
_runtime_lock = threading.Lock()


def _write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

DEFAULT_SOURCE_TYPE = "rtsp_camera"
_REQUIRED_RTSP_FIELDS = ("ip", "username", "password")


def load() -> Optional[dict]:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(config: dict) -> None:
    """Merge into the registered-profile file before overwriting. @claude"""
    with _config_lock:
        existing = load() or {}
        existing.update(config)
        existing.pop("name", None)  # @claude Drop a legacy field.
        existing.pop("stream_protocol", None)  # Drop legacy runtime transport preference.
        existing.pop("ptz_home", None)  # @claude The home moved to the applied slot.
        _write_json(CONFIG_PATH, existing)


def load_applied() -> dict:
    try:
        with open(APPLIED_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_applied(data: dict) -> None:
    with _config_lock:
        _write_json(APPLIED_PATH, data)


def save_patrol(patrol: dict) -> None:
    """Persist the auto-patrol setting (FR-052) into the applied slot. The
    setting survives camera switches — patrol without presets simply idles. @claude"""
    with _config_lock:
        applied = load_applied()
        applied["ptz_patrol"] = patrol
        _write_json(APPLIED_PATH, applied)


def save_presets(presets: dict | None) -> None:
    """Persist the PTZ presets into the applied slot — the positions belong to
    the camera the system is (or was last) connected to, not to registration. @claude"""
    with _config_lock:
        applied = load_applied()
        applied["ptz_presets"] = presets or {}
        applied.pop("ptz_home", None)  # @claude Drop the single-home legacy field.
        _write_json(APPLIED_PATH, applied)


def profile_view() -> dict:
    config = load()
    if not config:
        return {"configured": False}
    return _profile_view(config)


def register(config: dict) -> dict:
    """Persist a profile into the registered slot (FR-009, FR-010). Never
    touches MediaMTX or PTZ — connection happens at streaming start (FR-048).
    Returns {"ok": True} on success. @claude"""
    existing = load() or {}
    normalized, error = _normalize_profile(config, existing)
    if error:
        return {"ok": False, "error": error}
    save(normalized)
    return {"ok": True}


def streaming_start() -> dict:
    """Promote the registered profile to the applied slot and connect the
    source (FR-048). Idempotent; doubles as a restart. The whole
    promote-activate-persist sequence runs under the runtime lock. @claude"""
    with _runtime_lock:
        registered = load()
        if registered is None:
            return {"ok": False, "error": "no registered profile"}
        config, error = _normalize_profile(registered, registered)
        if error:
            return {"ok": False, "error": error}

        applied = load_applied()
        previous = applied.get("profile") or {}
        ptz_presets = applied.get("ptz_presets")
        if previous.get("ip") != config["ip"]:
            # @claude The presets belong to the camera: a different connection
            # @claude target invalidates the stored coordinates.
            ptz_presets = None

        if not _activate_runtime(config):
            return {"ok": False, "error": "MediaMTX API connection failed"}

        _save_applied({
            "streaming_active": True,
            "profile": config,
            "ptz_presets": ptz_presets or {},
            # @claude Patrol is a behavior setting, not camera-bound state —
            # @claude it survives the promote (FR-052).
            "ptz_patrol": applied.get("ptz_patrol") or ptz.get_patrol(),
        })
        ptz.load_presets(ptz_presets)
        return {"ok": True}


def streaming_stop() -> dict:
    """Detach the source (FR-049). The applied slot keeps the last-connected
    profile and home; only the active flag drops. Runs under the runtime lock
    so it cannot interleave with a start or a restore attempt. @claude"""
    with _runtime_lock:
        with _config_lock:
            applied = load_applied()
            applied["streaming_active"] = False
            _write_json(APPLIED_PATH, applied)
        # @claude Stop severs the camera relationship entirely (SDD §4.2):
        # @claude PTZ commands and polling end with the stream — symmetric
        # @claude with a restart in the stopped state. The home stays in the
        # @claude applied slot for the next start.
        ptz.clear_config()
        if not _patch_source(MEDIAMTX_SOURCE_DETACHED):
            return {"ok": False, "error": "MediaMTX API connection failed"}
        return {"ok": True}


# @claude Single-flight guard: the supervisor spawns a new startup_apply after
# @claude every MediaMTX restart, and the retry below is unbounded — without
# @claude this, a flapping child would accumulate retry threads.
_startup_apply_running = threading.Lock()


def startup_apply() -> None:
    """Restore the pre-restart streaming state (FR-014): reconnect with the
    applied profile only when streaming was active. Retries without a cap,
    mirroring the stream-connect retry (FR-046). Each attempt runs under the
    runtime lock and re-reads the applied slot there, so a streaming stop
    aborts the loop, a streaming start issued meanwhile wins with its newer
    profile, and neither can slip between the read and the patch. @claude"""
    if not _startup_apply_running.acquire(blocking=False):
        return
    try:
        if not load_applied().get("streaming_active"):
            log.info("Streaming was not active — nothing to restore")
            return

        # @claude The streamer may not be ready yet; retry with exponential backoff (FR-015).
        delay = 1.0
        attempt = 0
        while True:
            attempt += 1
            with _runtime_lock:
                applied = load_applied()
                if not applied.get("streaming_active"):
                    log.info("Streaming stopped while retrying — restore aborted")
                    return
                config = applied.get("profile")
                if not config:
                    log.error("Applied slot has no profile — cannot restore streaming")
                    return
                if _activate_runtime(config):
                    log.info("MediaMTX source configured (attempt %d)", attempt)
                    return
            log.warning("MediaMTX connection failed (attempt %d, retry in %.0fs)", attempt, delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)
    finally:
        _startup_apply_running.release()


def status_view() -> dict:
    """Streaming/profile state for the monitoring merge (SDD §6.4 (4)). @claude"""
    registered = load()
    applied = load_applied()
    pending = False
    if registered is not None:
        normalized, error = _normalize_profile(registered, registered)
        # @claude An invalid registered profile counts as pending: it differs
        # @claude from what the connection uses.
        pending = True if error else normalized != (applied.get("profile") or {})
    return {
        "profile_configured": registered is not None,
        "streaming_active": bool(applied.get("streaming_active")),
        "profile_pending": pending,
    }


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
        **{k: v for k, v in config.items() if k not in {"password", "stream_protocol"}},
        "password_set": bool(config.get("password")),
    }


def _configure_ptz(config: dict) -> None:
    if not config.get("onvif_port"):
        ptz.clear_config()
        return
    ptz.configure(_build_onvif_url(config), config["username"], config["password"])


def _apply_mediamtx_source(config: dict) -> bool:
    return _patch_source(_build_rtsp_url(config))


def _activate_runtime(config: dict, configure_ptz: bool = True) -> bool:
    activator = _source_runtime_activator(_source_type(config))
    if activator is None:
        return False
    return activator(config, configure_ptz=configure_ptz)


def _activate_rtsp_camera_runtime(config: dict, configure_ptz: bool = True) -> bool:
    # @claude Source first, PTZ second (SDD §4.2): PTZ configuration is an
    # @claude in-memory assignment that cannot fail, so this order leaves no
    # @claude partial state when the MediaMTX patch fails — the stream and the
    # @claude PTZ target never point at different cameras.
    if not _apply_mediamtx_source(config):
        return False
    if configure_ptz:
        _configure_ptz(config)
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


def _patch_source(source: str) -> bool:
    body: dict = {"source": source}
    if source != MEDIAMTX_SOURCE_DETACHED:
        body["sourceProtocol"] = "tcp"
    url = f"{MEDIAMTX_API}/v3/config/paths/patch/{MEDIAMTX_PATH_NAME}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        log.error("MediaMTX API error: %s", e)
        return False

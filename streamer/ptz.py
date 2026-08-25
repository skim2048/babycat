"""
ONVIF PTZ control module.

ContinuousMove / Stop / AbsoluteMove / GetStatus polling, authenticated
with SOAP + WS-Security (UsernameToken). Pan and tilt only: the camera in
use has no zoom, and zoom is outside the product scope (SRS §2.4).

@claude
"""

import base64
import datetime
import hashlib
import logging
import os
import re
import threading
import time
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

# @claude Fallback ProfileToken when GetProfiles fails; the token is resolved
# @claude from the camera on first use (_profile_token).
_PTZ_PROFILE_FALLBACK = "profile_1"

PRESET_SLOTS = (1, 2, 3, 4)

# @claude A manual continuous move is assumed over after this long without a
# @claude stop: a client that never sends "stop" must not block patrol forever.
MOVE_HOLD_S = 10.0

_lock    = threading.Lock()
_current: dict = {"pan": None, "tilt": None}
_presets: dict = {}  # slot(int) -> {"pan": float, "tilt": float}
_moving_until: float = 0.0
_profile_token: Optional[str] = None

_ONVIF_URL:  Optional[str] = None
_ONVIF_USER: Optional[str] = None
_ONVIF_PASS: Optional[str] = None


def configure(url: str, user: str, password: str) -> None:
    global _ONVIF_URL, _ONVIF_USER, _ONVIF_PASS, _profile_token
    with _lock:
        _ONVIF_URL  = url
        _ONVIF_USER = user
        _ONVIF_PASS = password
        _profile_token = None
    log.info("PTZ configured: %s", url)


def clear_config() -> None:
    global _ONVIF_URL, _ONVIF_USER, _ONVIF_PASS, _moving_until, _profile_token
    with _lock:
        _ONVIF_URL = None
        _ONVIF_USER = None
        _ONVIF_PASS = None
        _moving_until = 0.0
        _profile_token = None
        _current.update({"pan": None, "tilt": None})
    log.info("PTZ disabled")


def is_configured() -> bool:
    with _lock:
        return _ONVIF_URL is not None


def is_moving() -> bool:
    with _lock:
        return time.monotonic() < _moving_until


def set_moving(value: bool) -> None:
    global _moving_until
    with _lock:
        _moving_until = time.monotonic() + MOVE_HOLD_S if value else 0.0


def get_current() -> dict:
    with _lock:
        return dict(_current)


def get_preset(slot: int) -> Optional[dict]:
    with _lock:
        preset = _presets.get(slot)
        return dict(preset) if preset else None


def get_presets() -> dict:
    with _lock:
        return {slot: dict(preset) for slot, preset in _presets.items()}


# ── ONVIF SOAP ───────────────────────────────────────────────────────────────

def _auth_header() -> str:
    with _lock:
        user = _ONVIF_USER
        passwd = _ONVIF_PASS
    nonce_raw = os.urandom(20)
    nonce_b64 = base64.b64encode(nonce_raw).decode()
    created   = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest    = base64.b64encode(
        hashlib.sha1(nonce_raw + created.encode() + passwd.encode()).digest()
    ).decode()
    return (
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
        ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{user}</wsse:Username>"
        f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>'
        f'<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>'
        f"<wsu:Created>{created}</wsu:Created>"
        "</wsse:UsernameToken></wsse:Security>"
    )


def _post(body: str) -> str:
    with _lock:
        url = _ONVIF_URL
    soap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        f"<s:Header>{_auth_header()}</s:Header>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    )
    req = urllib.request.Request(
        url,
        data=soap.encode(),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.read().decode()


def _issue_request(body: str, operation: str) -> Optional[str]:
    if not is_configured():
        return None
    try:
        return _post(body)
    except Exception as e:
        log.error("%s failed: %s", operation, e)
        return None


def _resolve_profile_token() -> str:
    """Ask the camera for its media profiles and use the first token; fall
    back to the conventional name when the call fails. Cached until the PTZ
    target changes. @claude"""
    global _profile_token
    with _lock:
        if _profile_token:
            return _profile_token
    text = _issue_request(
        '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>', "GetProfiles"
    )
    m = re.search(r'Profiles[^>]*\stoken="([^"]+)"', text or "")
    token = m.group(1) if m else _PTZ_PROFILE_FALLBACK
    if not m:
        log.warning("GetProfiles gave no token — using %s", token)
    with _lock:
        _profile_token = token
    return token


# ── PTZ commands ─────────────────────────────────────────────────────────────

def move(pan: float, tilt: float) -> None:
    body = (
        f'<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_resolve_profile_token()}</ProfileToken>"
        f'<Velocity><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.2f}" y="{tilt:.2f}"/></Velocity>'
        f"</ContinuousMove>"
    )
    _issue_request(body, "move")


def stop() -> None:
    body = (
        f'<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_resolve_profile_token()}</ProfileToken>"
        "<PanTilt>true</PanTilt><Zoom>false</Zoom>"
        "</Stop>"
    )
    _issue_request(body, "stop")


def absolute_move(pan: float, tilt: float) -> None:
    body = (
        f'<AbsoluteMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_resolve_profile_token()}</ProfileToken>"
        f'<Position><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.3f}" y="{tilt:.3f}"/></Position>'
        f"</AbsoluteMove>"
    )
    _issue_request(body, "absolute move")


def get_status() -> Optional[dict]:
    body = (
        f'<GetStatus xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_resolve_profile_token()}</ProfileToken>"
        "</GetStatus>"
    )
    text = _issue_request(body, "GetStatus")
    if not text:
        return None
    m = re.search(r'PanTilt[^/]* x="([^"]*)"[^/]* y="([^"]*)"', text)
    if m:
        return {"pan": round(float(m.group(1)), 3),
                "tilt": round(float(m.group(2)), 3)}
    return None


# ── Preset save/load ─────────────────────────────────────────────────────────

def load_presets(data: Optional[dict]) -> None:
    """Apply a ptz_presets mapping read from the applied slot. An empty value
    resets the in-memory presets — a profile switch that invalidated the stored
    positions (SDD §4.2) must not leave the previous camera's coordinates
    lingering in memory. JSON round-trips slot keys as strings. @claude"""
    global _presets
    loaded: dict = {}
    for key, value in (data or {}).items():
        try:
            slot = int(key)
            if slot not in PRESET_SLOTS:
                continue
            loaded[slot] = {
                "pan":  round(float(value["pan"]),  3),
                "tilt": round(float(value["tilt"]), 3),
            }
        except (KeyError, TypeError, ValueError) as e:
            log.error("Preset %s load failed: %s", key, e)
    with _lock:
        _presets = loaded
    if loaded:
        log.info("Presets loaded: %s", sorted(loaded))


def save_preset(slot: int) -> Optional[dict]:
    """Save the current position into the slot. Returns the full presets
    mapping for the caller to persist, or None when the current position is
    unknown or the slot is invalid. @claude"""
    if slot not in PRESET_SLOTS:
        return None
    with _lock:
        cur = dict(_current)
    if cur["pan"] is None:
        return None
    with _lock:
        _presets[slot] = {"pan": cur["pan"], "tilt": cur["tilt"]}
        snapshot = {s: dict(p) for s, p in _presets.items()}
    log.info("Preset %d saved: pan=%s, tilt=%s", slot, cur["pan"], cur["tilt"])
    return snapshot


# ── Polling loop ─────────────────────────────────────────────────────────────

def poll_loop() -> None:
    """Background thread: poll the current PTZ position every 2 seconds. @claude"""
    while True:
        poll_once()
        time.sleep(2)


def poll_once() -> None:
    """Poll PTZ status once and update the current position when available."""
    status = get_status()
    if status:
        with _lock:
            _current.update(status)


# ── Auto patrol (FR-052) ─────────────────────────────────────────────────────

PATROL_MIN_INTERVAL_S = 5
PATROL_DEFAULT_INTERVAL_S = 30

# @claude slot: 순찰이 마지막으로 이동시킨 프리셋 슬롯. 순찰을 꺼도 값을
# @claude 유지하여, 클라이언트가 카메라가 멈춰 선 위치의 프리셋을 계속
# @claude 가리킬 수 있게 한다. 프리셋 무효화·재기동 시에만 None이 된다.
_patrol: dict = {"enabled": False, "interval_s": PATROL_DEFAULT_INTERVAL_S, "slot": None}


def get_patrol() -> dict:
    with _lock:
        return dict(_patrol)


def set_patrol(enabled: bool, interval_s: Optional[int] = None) -> dict:
    with _lock:
        was_enabled = _patrol["enabled"]
        _patrol["enabled"] = bool(enabled)
        if interval_s is not None:
            _patrol["interval_s"] = max(PATROL_MIN_INTERVAL_S, int(interval_s))
    # @claude 순찰을 끄면 카메라를 프리셋 1로 복귀시킨다(위치·표시 모두).
    # @claude 프리셋 1이 없으면 복귀 없이 슬롯 표시만 비운다.
    if was_enabled and not enabled:
        home = get_preset(1)
        with _lock:
            _patrol["slot"] = 1 if home else None
        if home:
            threading.Thread(
                target=absolute_move, args=(home["pan"], home["tilt"]), daemon=True
            ).start()
    return get_patrol()


def load_patrol(data: Optional[dict]) -> None:
    """Apply a ptz_patrol mapping read from the applied slot. Invalid or
    missing values fall back to the defaults; the runtime slot always starts
    empty. @claude"""
    if not isinstance(data, dict):
        return
    with _lock:
        _patrol["enabled"] = bool(data.get("enabled", False))
        _patrol["slot"] = None
        try:
            _patrol["interval_s"] = max(
                PATROL_MIN_INTERVAL_S, int(data.get("interval_s", PATROL_DEFAULT_INTERVAL_S))
            )
        except (TypeError, ValueError):
            _patrol["interval_s"] = PATROL_DEFAULT_INTERVAL_S


def patrol_loop() -> None:
    """Background thread: cycle through the saved presets in slot order while
    patrol is enabled. A tick is skipped while a manual continuous move is in
    progress, and the cycle idles when PTZ is unconfigured or no preset
    exists. Toggling patrol off resets the schedule, so re-enabling moves to
    the next preset immediately. @claude"""
    idx = 0
    next_due = None
    while True:
        time.sleep(1)
        with _lock:
            enabled = _patrol["enabled"]
            interval = _patrol["interval_s"]
            slots = sorted(_presets)
        if not slots:
            # @claude 프리셋이 무효화되면(카메라 교체 등) 순회 슬롯 표시도 무효다.
            with _lock:
                _patrol["slot"] = None
        if not enabled or not slots or not is_configured():
            next_due = None
            continue
        now = time.monotonic()
        if next_due is not None and now < next_due:
            continue
        if is_moving():
            continue
        slot = slots[idx % len(slots)]
        preset = get_preset(slot)
        idx += 1
        next_due = now + interval
        if preset:
            with _lock:
                _patrol["slot"] = slot
            absolute_move(preset["pan"], preset["tilt"])

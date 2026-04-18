"""
ONVIF PTZ control module.

ContinuousMove / Stop / AbsoluteMove / GetStatus polling, authenticated
with SOAP + WS-Security (UsernameToken).

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

_PTZ_PROFILE = "profile_1"
_PTZ_SPEED   = 0.5

_lock    = threading.Lock()
_current: dict = {"pan": None, "tilt": None}
_saved:   dict = {"pan": None, "tilt": None}
_moving:  bool = False

_ONVIF_URL:  Optional[str] = None
_ONVIF_USER: Optional[str] = None
_ONVIF_PASS: Optional[str] = None


def configure(url: str, user: str, password: str) -> None:
    global _ONVIF_URL, _ONVIF_USER, _ONVIF_PASS
    with _lock:
        _ONVIF_URL  = url
        _ONVIF_USER = user
        _ONVIF_PASS = password
    log.info("PTZ configured: %s", url)


def is_configured() -> bool:
    with _lock:
        return _ONVIF_URL is not None


def is_moving() -> bool:
    with _lock:
        return _moving


def set_moving(value: bool) -> None:
    global _moving
    with _lock:
        _moving = value


def get_current() -> dict:
    with _lock:
        return dict(_current)


def get_saved() -> dict:
    with _lock:
        return dict(_saved)


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


# ── PTZ commands ─────────────────────────────────────────────────────────────

def move(pan: float, tilt: float) -> None:
    if not is_configured():
        return
    body = (
        f'<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        f'<Velocity><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.2f}" y="{tilt:.2f}"/></Velocity>'
        f"</ContinuousMove>"
    )
    try:
        _post(body)
    except Exception as e:
        log.error("move failed: %s", e)


def stop() -> None:
    if not is_configured():
        return
    body = (
        f'<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        "<PanTilt>true</PanTilt><Zoom>false</Zoom>"
        "</Stop>"
    )
    try:
        _post(body)
    except Exception as e:
        log.error("stop failed: %s", e)


def absolute_move(pan: float, tilt: float) -> None:
    if not is_configured():
        return
    body = (
        f'<AbsoluteMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        f'<Position><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.3f}" y="{tilt:.3f}"/></Position>'
        f"</AbsoluteMove>"
    )
    try:
        _post(body)
    except Exception as e:
        log.error("absolute move failed: %s", e)


def get_status() -> Optional[dict]:
    if not is_configured():
        return None
    body = (
        f'<GetStatus xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        "</GetStatus>"
    )
    try:
        text = _post(body)
        m = re.search(r'PanTilt[^/]* x="([^"]*)"[^/]* y="([^"]*)"', text)
        if m:
            return {"pan": round(float(m.group(1)), 3),
                    "tilt": round(float(m.group(2)), 3)}
    except Exception as e:
        log.error("GetStatus failed: %s", e)
    return None


# ── Home position save/load ──────────────────────────────────────────────────

def load_home(data: Optional[dict]) -> None:
    """Apply a ptz_home dict read from the saved profile. @claude"""
    global _saved
    if not data:
        return
    try:
        with _lock:
            _saved = {
                "pan":  round(float(data["pan"]),  3),
                "tilt": round(float(data["tilt"]), 3),
            }
        log.info("Home position loaded: %s", _saved)
    except (KeyError, ValueError) as e:
        log.error("Home position load failed: %s", e)


def save_home() -> Optional[dict]:
    """Save the current position as home. Caller must persist the return value into the profile. @claude"""
    with _lock:
        cur = dict(_current)
    if cur["pan"] is None:
        return None
    with _lock:
        _saved.update(cur)
    log.info("Home position saved: pan=%s, tilt=%s", cur["pan"], cur["tilt"])
    return {"pan": cur["pan"], "tilt": cur["tilt"]}


# ── Polling loop ─────────────────────────────────────────────────────────────

def poll_loop() -> None:
    """Background thread: poll the current PTZ position every 2 seconds. @claude"""
    while True:
        if is_configured():
            status = get_status()
            if status:
                with _lock:
                    _current.update(status)
        time.sleep(2)

"""
ONVIF PTZ 제어 모듈

ContinuousMove / Stop / AbsoluteMove / GetStatus 폴링.
SOAP + WS-Security(UsernameToken) 인증.
"""

import base64
import datetime
import hashlib
import os
import re
import threading
import time
import urllib.request
from typing import Optional


_ONVIF_URL   = "http://192.168.1.101:2020/onvif/service"
_ONVIF_USER  = "tapoadmin"
_ONVIF_PASS  = "ace4421000!"
_PTZ_PROFILE = "profile_1"
_PTZ_SPEED   = 0.5
_PTZ_HOME_FILE = "/app/ptz_home.txt"

_lock    = threading.Lock()
_current: dict = {"pan": None, "tilt": None}
_saved:   dict = {"pan": None, "tilt": None}
_moving:  bool = False


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
    nonce_raw = os.urandom(20)
    nonce_b64 = base64.b64encode(nonce_raw).decode()
    created   = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    digest    = base64.b64encode(
        hashlib.sha1(nonce_raw + created.encode() + _ONVIF_PASS.encode()).digest()
    ).decode()
    return (
        '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"'
        ' xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{_ONVIF_USER}</wsse:Username>"
        f'<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>'
        f'<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>'
        f"<wsu:Created>{created}</wsu:Created>"
        "</wsse:UsernameToken></wsse:Security>"
    )


def _post(body: str) -> str:
    soap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        f"<s:Header>{_auth_header()}</s:Header>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    )
    req = urllib.request.Request(
        _ONVIF_URL,
        data=soap.encode(),
        headers={"Content-Type": "application/soap+xml; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        return resp.read().decode()


# ── PTZ 명령 ─────────────────────────────────────────────────────────────────

def move(pan: float, tilt: float) -> None:
    body = (
        f'<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        f'<Velocity><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.2f}" y="{tilt:.2f}"/></Velocity>'
        f"</ContinuousMove>"
    )
    try:
        _post(body)
    except Exception as e:
        print(f"[PTZ] move 실패: {e}", flush=True)


def stop() -> None:
    body = (
        f'<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        "<PanTilt>true</PanTilt><Zoom>false</Zoom>"
        "</Stop>"
    )
    try:
        _post(body)
    except Exception as e:
        print(f"[PTZ] stop 실패: {e}", flush=True)


def absolute_move(pan: float, tilt: float) -> None:
    body = (
        f'<AbsoluteMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        f"<ProfileToken>{_PTZ_PROFILE}</ProfileToken>"
        f'<Position><PanTilt xmlns="http://www.onvif.org/ver10/schema" x="{pan:.3f}" y="{tilt:.3f}"/></Position>'
        f"</AbsoluteMove>"
    )
    try:
        _post(body)
    except Exception as e:
        print(f"[PTZ] absolute move 실패: {e}", flush=True)


def get_status() -> Optional[dict]:
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
        print(f"[PTZ] GetStatus 실패: {e}", flush=True)
    return None


# ── 홈 위치 저장/로드 ────────────────────────────────────────────────────────

def load_home() -> None:
    global _saved
    try:
        with open(_PTZ_HOME_FILE) as f:
            data = dict(line.strip().split("=") for line in f if "=" in line)
        with _lock:
            _saved = {
                "pan":  round(float(data["pan"]),  3),
                "tilt": round(float(data["tilt"]), 3),
            }
        print(f"[PTZ] 저장 위치 로드: {_saved}", flush=True)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[PTZ] 저장 위치 로드 실패: {e}", flush=True)


def save_home() -> bool:
    with _lock:
        cur = dict(_current)
    if cur["pan"] is None:
        return False
    try:
        with open(_PTZ_HOME_FILE, "w") as f:
            f.write(f"pan={cur['pan']}\ntilt={cur['tilt']}\n")
        with _lock:
            _saved.update(cur)
        print(f"[PTZ] 위치 저장: pan={cur['pan']}, tilt={cur['tilt']}", flush=True)
        return True
    except Exception as e:
        print(f"[PTZ] 위치 저장 실패: {e}", flush=True)
        return False


# ── 폴링 루프 ────────────────────────────────────────────────────────────────

def poll_loop() -> None:
    """백그라운드 스레드: 2초마다 현재 PTZ 위치 폴링."""
    while True:
        status = get_status()
        if status:
            with _lock:
                _current.update(status)
        time.sleep(2)

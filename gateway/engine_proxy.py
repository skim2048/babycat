"""Helpers for proxying selected Engine-container contracts through the Gateway."""

import json
import urllib.error
import urllib.request

from fastapi import HTTPException, Request

from schemas import ApplyResultOut, CameraProfileOut


def request_auth_header(request: Request) -> str | None:
    """Preserve the inbound Authorization header for upstream Engine proxy calls."""
    return request.headers.get("Authorization")


def proxy_engine(
    engine_internal_url: str,
    method: str,
    path: str,
    auth_header: str | None,
    body: dict | None = None,
    timeout: int = 10,
):
    """Proxy a request to the App container's internal HTTP server; returns (status, json)."""
    url = f"{engine_internal_url}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if auth_header:
        req.add_header("Authorization", auth_header)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode()
            return response.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        return e.code, (json.loads(text) if text else None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")


def camera_profile_out(data: dict | None) -> CameraProfileOut:
    """Normalize the proxied camera profile for clients and mask stored secrets."""
    if not data:
        return CameraProfileOut(configured=False)

    sanitized = dict(data)
    password = sanitized.pop("password", None)
    upstream_password_set = sanitized.get("password_set")
    sanitized["password_set"] = bool(upstream_password_set) or bool(password)
    return CameraProfileOut(**sanitized)


def camera_apply_out(status: int, data: dict | None) -> ApplyResultOut:
    """Normalize proxied camera-apply responses into the public API contract."""
    if status >= 500:
        raise HTTPException(status_code=502, detail="upstream error")
    return ApplyResultOut(**(data or {"ok": False, "error": "no response"}))

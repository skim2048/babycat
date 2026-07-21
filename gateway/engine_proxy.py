"""Helpers for proxying selected Engine-container contracts through the Gateway."""

import json
import urllib.error
import urllib.request

from fastapi import HTTPException, Request

from schemas import ApplyResultOut, CameraProfileOut


def request_auth_header(request: Request) -> str | None:
    """
    Build the Authorization header for upstream Engine proxy calls.

    Falls back to the ?token= query parameter, which require_auth also
    accepts, so header-less clients (EventSource, <img src>) still
    authenticate upstream.

    @claude
    """
    header = request.headers.get("Authorization")
    if header:
        return header
    token = request.query_params.get("token")
    return f"Bearer {token}" if token else None


def proxy_engine(
    engine_internal_url: str,
    method: str,
    path: str,
    auth_header: str | None,
    body: dict | None = None,
    timeout: int = 10,
):
    """Proxy a request to the Engine container's internal HTTP server; returns (status, json)."""
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


def open_engine_stream(
    engine_internal_url: str,
    path: str,
    auth_header: str | None,
):
    """
    Open an unbounded upstream response (SSE, MJPEG) and hand back the raw
    connection. No read timeout: these responses stay open by design, and an
    idle SSE channel must not be mistaken for a stalled one.

    @claude
    """
    req = urllib.request.Request(f"{engine_internal_url}{path}", method="GET")
    if auth_header:
        req.add_header("Authorization", auth_header)
    try:
        return urllib.request.urlopen(req, timeout=None)
    except urllib.error.HTTPError as e:
        e.close()
        raise HTTPException(status_code=e.code, detail="upstream rejected the request")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")


def iter_engine_stream(response, chunk_size: int = 8192):
    """
    Relay an upstream stream chunk by chunk. read1() returns as soon as any
    bytes arrive, so an SSE event is forwarded when it is produced rather
    than held back until a full buffer accumulates.

    @claude
    """
    try:
        while True:
            chunk = response.read1(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        response.close()


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

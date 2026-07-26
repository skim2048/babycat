"""
Router-side authentication (SDD §4.1, §6.2).

Two steps per request: verify the JWT signature/expiry locally with the
shared secret, then compare the token's epoch claim against the account's
current epoch from the manager. The epoch comparison is what makes
logout/password-change revocation immediate (FR-003, FR-005).

@claude
"""

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import urlsafe_b64decode

from fastapi import HTTPException, Request

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
MANAGER_URL = os.environ.get("MANAGER_URL", "http://manager:8100")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return urlsafe_b64decode(s + "=" * padding)


def verify_token(token: str) -> dict | None:
    """Verify signature and expiry. Returns the payload dict if valid, else None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        expected_sig = hmac.new(
            JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url_decode(sig), expected_sig):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def _current_epoch(username: str) -> int:
    """Ask the manager for the account's current token epoch. Fail closed. @claude"""
    url = f"{MANAGER_URL}/internal/epoch?username={urllib.parse.quote(username)}"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return int(data["epoch"])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(status_code=401, detail="unknown user")
        raise HTTPException(status_code=502, detail="auth backend unavailable")
    except Exception:
        raise HTTPException(status_code=502, detail="auth backend unavailable")


def require_auth(request: Request) -> dict:
    """FastAPI Depends helper. Validates Authorization: Bearer <token>, or ?token=<token>
    as a fallback for clients that cannot set headers (EventSource, <video src>, HLS).

    @claude
    """
    auth_header = request.headers.get("Authorization", "")
    token: str | None = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    if payload.get("epoch", -1) != _current_epoch(payload.get("sub", "")):
        raise HTTPException(status_code=401, detail="token revoked")
    return payload

"""
Pure helper functions for the app HTTP server.

Keeps token verification and clip-file resolution separate from the
BaseHTTPRequestHandler transport code in server.py.
"""

import hashlib
import hmac
import json
import re
import time
from base64 import urlsafe_b64decode
from pathlib import Path


def verify_jwt(token: str, secret: str, now: float | None = None) -> bool:
    """Verify JWT (HMAC-SHA256) signature and expiry."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        header, payload, sig = parts
        expected = hmac.new(
            secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        padding = 4 - len(sig) % 4
        actual = urlsafe_b64decode(sig + "=" * padding)
        if not hmac.compare_digest(actual, expected):
            return False
        padding = 4 - len(payload) % 4
        data = json.loads(urlsafe_b64decode(payload + "=" * padding))
        current = time.time() if now is None else now
        return data.get("exp", 0) >= current
    except Exception:
        return False


def resolve_clip_file(clip_dir: str, name: str) -> Path | None:
    """
    Resolve a clip filename under the clip directory.

    Names are expected to start with YYYYMMDD_, so try the inferred
    year/month path first, then fall back to recursive search.
    """
    if not clip_dir:
        return None
    if "/" in name or "\\" in name or ".." in name:
        return None

    base = Path(clip_dir)
    if len(name) >= 8 and name[:8].isdigit():
        yyyy, mm = name[:4], name[4:6]
        candidate = base / yyyy / mm / name
        if candidate.exists() and candidate.is_file():
            return candidate

    for path in base.rglob(name):
        if path.is_file():
            return path
    return None


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a simple bytes=start-end header into an inclusive range."""
    match = re.match(r"bytes=(\d+)-(\d*)", range_header or "")
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return None
    return start, end

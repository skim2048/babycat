import base64
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import server_support  # noqa: E402


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _make_jwt(secret: str, payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    signature = hmac.new(
        secret.encode(),
        f"{header}.{body}".encode(),
        hashlib.sha256,
    ).digest()
    return f"{header}.{body}.{_b64url(signature)}"


def test_verify_jwt_accepts_valid_token():
    token = _make_jwt("secret", {"exp": 200})
    assert server_support.verify_jwt(token, "secret", now=100) is True


def test_verify_jwt_rejects_expired_token():
    token = _make_jwt("secret", {"exp": 50})
    assert server_support.verify_jwt(token, "secret", now=100) is False


def test_resolve_clip_file_prefers_inferred_year_month_path(tmp_path: Path):
    clip_dir = tmp_path / "clips"
    target = clip_dir / "2026" / "04"
    target.mkdir(parents=True)
    file_path = target / "20260423_120000_001.mp4"
    file_path.write_bytes(b"data")

    resolved = server_support.resolve_clip_file(str(clip_dir), file_path.name)

    assert resolved == file_path


def test_parse_range_header_accepts_open_end_range():
    assert server_support.parse_range_header("bytes=10-", 100) == (10, 99)


def test_parse_range_header_rejects_invalid_range():
    assert server_support.parse_range_header("bytes=120-130", 100) is None

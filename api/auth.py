"""Babycat — JWT authentication (login, token verification, user management)."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import Depends, HTTPException, Request

from database import get_db

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_EXPIRY = int(os.environ.get("JWT_EXPIRY", "3600"))  # 1시간 기본
REFRESH_EXPIRY = int(os.environ.get("REFRESH_EXPIRY", str(60 * 60 * 24 * 30)))  # 30일 기본

DEFAULT_USER = os.environ.get("DEFAULT_USER", "admin")
DEFAULT_PASS = os.environ.get("DEFAULT_PASS", "admin")

# ── 로그인 시도 제한 (인메모리) ─────────────────────────────────────────────
# { username: { "count": int, "locked_until": float } }
_login_attempts: dict[str, dict] = {}
# 10회 실패 → 30분 잠금, 이후 반복
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_SECONDS = 1800  # 30분


# ── Schema ──────────────────────────────────────────────────────────────────

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL UNIQUE,
    password_hash    TEXT    NOT NULL,
    salt             TEXT    NOT NULL,
    password_changed INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT    NOT NULL UNIQUE,
    username    TEXT    NOT NULL,
    expires_at  INTEGER NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_username ON refresh_tokens(username);
"""


def init_users(db: sqlite3.Connection) -> None:
    """users 테이블 생성 및 기본 계정 시딩."""
    db.executescript(USERS_SCHEMA)
    # password_changed 컬럼이 없으면 추가 (기존 DB 마이그레이션)
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
    if "password_changed" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN password_changed INTEGER NOT NULL DEFAULT 0")
        db.commit()
    row = db.execute(
        "SELECT id FROM users WHERE username = ?", (DEFAULT_USER,)
    ).fetchone()
    if not row:
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(DEFAULT_PASS, salt)
        db.execute(
            "INSERT INTO users (username, password_hash, salt, password_changed) "
            "VALUES (?, ?, ?, 0)",
            (DEFAULT_USER, pw_hash, salt),
        )
        db.commit()


# ── Password ────────────────────────────────────────────────────────────────


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


def _verify_password(password: str, salt: str, pw_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password, salt), pw_hash)


# ── JWT (HMAC-SHA256, 외부 라이브러리 없음) ─────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return urlsafe_b64decode(s + "=" * padding)


def create_token(username: str) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY,
    }).encode())
    signature = hmac.new(
        JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{_b64url_encode(signature)}"


def verify_token(token: str) -> dict:
    """토큰 검증. 유효하면 payload dict 반환, 아니면 None."""
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


# ── FastAPI 의존성 ──────────────────────────────────────────────────────────


def require_auth(request: Request) -> dict:
    """FastAPI Depends 용. Authorization: Bearer <token> 또는 ?token=<token> 검증.

    query token fallback은 헤더를 못 보내는 클라이언트 (EventSource, <video src>) 용.
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
    return payload


# ── 로그인 시도 제한 ─────────────────────────────────────────────────────────


def _get_lockout_seconds(count: int) -> int:
    """실패 횟수에 따른 잠금 시간(초) 반환."""
    if count >= _LOCKOUT_THRESHOLD:
        return _LOCKOUT_SECONDS
    return 0


def check_lockout(username: str) -> int:
    """잠금 상태 확인. 잠겨 있으면 남은 초 반환, 아니면 0."""
    record = _login_attempts.get(username)
    if not record:
        return 0
    remaining = record["locked_until"] - time.time()
    if remaining > 0:
        return int(remaining) + 1
    return 0


def record_failure(username: str) -> int:
    """실패 기록. 잠금이 걸리면 잠금 시간(초) 반환, 아니면 0."""
    record = _login_attempts.setdefault(username, {"count": 0, "locked_until": 0.0})
    record["count"] += 1
    lockout = _get_lockout_seconds(record["count"])
    if lockout > 0:
        record["locked_until"] = time.time() + lockout
    return lockout


def clear_failure(username: str) -> None:
    """로그인 성공 시 실패 기록 초기화."""
    _login_attempts.pop(username, None)


# ── 로그인 처리 ─────────────────────────────────────────────────────────────


def authenticate(
    username: str, password: str, db: sqlite3.Connection, remember_me: bool = False
) -> dict | None:
    """
    인증 처리.
    성공 시 {"token", "must_change_password", "refresh_token"?} 반환.
    잠금 상태면 HTTPException(429) 발생.
    실패 시 None.
    """
    # 잠금 확인
    remaining = check_lockout(username)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"too many attempts, retry after {remaining}s",
            headers={"Retry-After": str(remaining)},
        )

    row = db.execute(
        "SELECT password_hash, salt, password_changed FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row:
        record_failure(username)
        return None
    if not _verify_password(password, row["salt"], row["password_hash"]):
        record_failure(username)
        return None

    clear_failure(username)
    result = {
        "token": create_token(username),
        "must_change_password": not row["password_changed"],
        "refresh_token": None,
    }
    if remember_me:
        result["refresh_token"] = issue_refresh_token(username, db)
    return result


# ── Refresh Token ───────────────────────────────────────────────────────────


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(username: str, db: sqlite3.Connection) -> str:
    """새 refresh token 발급. 평문 토큰 반환, DB에는 해시만 저장."""
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + REFRESH_EXPIRY
    db.execute(
        "INSERT INTO refresh_tokens (token_hash, username, expires_at) VALUES (?, ?, ?)",
        (_hash_refresh(token), username, expires_at),
    )
    db.commit()
    return token


def consume_refresh_token(token: str, db: sqlite3.Connection) -> str | None:
    """refresh token 검증. 유효하면 username 반환, 아니면 None."""
    row = db.execute(
        "SELECT username, expires_at, revoked FROM refresh_tokens WHERE token_hash = ?",
        (_hash_refresh(token),),
    ).fetchone()
    if not row:
        return None
    if row["revoked"]:
        return None
    if row["expires_at"] < int(time.time()):
        return None
    return row["username"]


def revoke_refresh_token(token: str, db: sqlite3.Connection) -> bool:
    """refresh token 폐기. 폐기되었거나 존재하면 True, 없으면 False."""
    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (_hash_refresh(token),),
    )
    db.commit()
    return cur.rowcount > 0


def revoke_all_refresh_tokens(username: str, db: sqlite3.Connection) -> int:
    """특정 사용자의 모든 refresh token 폐기 (예: 비밀번호 변경 시)."""
    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE username = ? AND revoked = 0",
        (username,),
    )
    db.commit()
    return cur.rowcount


# ── 비밀번호 변경 ──────────────────────────────────────────────────────────


def change_password(
    username: str, current_password: str, new_password: str, db: sqlite3.Connection
) -> bool:
    """비밀번호 변경. 성공 시 True, 현재 비밀번호 불일치 시 False."""
    row = db.execute(
        "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        return False
    if not _verify_password(current_password, row["salt"], row["password_hash"]):
        return False
    new_salt = secrets.token_hex(16)
    new_hash = _hash_password(new_password, new_salt)
    db.execute(
        "UPDATE users SET password_hash = ?, salt = ?, password_changed = 1 "
        "WHERE username = ?",
        (new_hash, new_salt, username),
    )
    db.commit()
    # 비밀번호 변경 시 기존 refresh token 모두 폐기 (보안)
    revoke_all_refresh_tokens(username, db)
    return True

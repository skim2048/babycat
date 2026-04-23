"""Babycat — JWT authentication (login, token verification, user management). @claude"""

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
JWT_EXPIRY = int(os.environ.get("JWT_EXPIRY", "600"))  # @claude 10m default.
REFRESH_EXPIRY = int(os.environ.get("REFRESH_EXPIRY", str(60 * 60 * 24 * 30)))  # @claude 30d default.

DEFAULT_USER = os.environ.get("DEFAULT_USER", "admin")
DEFAULT_PASS = os.environ.get("DEFAULT_PASS", "admin")

# ── Login attempt limiter (in-memory) ────────────────────────────────────────
# @claude Shape: { username: { "count": int, "locked_until": float } }
_login_attempts: dict[str, dict] = {}
# @claude 10 failures -> 30-minute lockout, repeated for subsequent bursts.
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_SECONDS = 1800


# ── Schema ───────────────────────────────────────────────────────────────────

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
    """Create the users table and seed the default account. @claude"""
    db.executescript(USERS_SCHEMA)
    # @claude Migration: add the password_changed column when missing from older DBs.
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


# ── Password ─────────────────────────────────────────────────────────────────


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


def _verify_password(password: str, salt: str, pw_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password, salt), pw_hash)


# ── JWT (HMAC-SHA256; no external library) ───────────────────────────────────


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
    """Verify a token. Returns the payload dict if valid, else None. @claude"""
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


# ── FastAPI dependency ───────────────────────────────────────────────────────


def require_auth(request: Request) -> dict:
    """FastAPI Depends helper. Validates Authorization: Bearer <token>, or ?token=<token>
    as a fallback for clients that cannot set headers (EventSource, <video src>).

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
    return payload


# ── Login attempt limiter ────────────────────────────────────────────────────


def _get_lockout_seconds(count: int) -> int:
    """Return the lockout duration (seconds) for a given failure count. @claude"""
    if count >= _LOCKOUT_THRESHOLD:
        return _LOCKOUT_SECONDS
    return 0


def check_lockout(username: str) -> int:
    """Check lockout state; returns remaining seconds if locked, else 0. @claude"""
    record = _login_attempts.get(username)
    if not record:
        return 0
    remaining = record["locked_until"] - time.time()
    if remaining > 0:
        return int(remaining) + 1
    return 0


def record_failure(username: str) -> int:
    """Record a failure; returns lockout seconds when one is triggered, else 0. @claude"""
    record = _login_attempts.setdefault(username, {"count": 0, "locked_until": 0.0})
    record["count"] += 1
    lockout = _get_lockout_seconds(record["count"])
    if lockout > 0:
        record["locked_until"] = time.time() + lockout
    return lockout


def clear_failure(username: str) -> None:
    """Clear the failure counter on a successful login. @claude"""
    _login_attempts.pop(username, None)


# ── Authentication flow ──────────────────────────────────────────────────────


def authenticate(
    username: str, password: str, db: sqlite3.Connection, remember_me: bool = False
) -> dict | None:
    """
    Authenticate a user.
      - On success, returns {"token", "must_change_password", "refresh_token"?}.
      - On lockout, raises HTTPException(429).
      - On mismatch, returns None.

    @claude
    """
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


# ── Refresh Token ────────────────────────────────────────────────────────────


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(username: str, db: sqlite3.Connection) -> str:
    """Issue a new refresh token. Returns plaintext; the DB stores only the hash. @claude"""
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + REFRESH_EXPIRY
    db.execute(
        "INSERT INTO refresh_tokens (token_hash, username, expires_at) VALUES (?, ?, ?)",
        (_hash_refresh(token), username, expires_at),
    )
    db.commit()
    return token


def consume_refresh_token(token: str, db: sqlite3.Connection) -> str | None:
    """Validate a refresh token. Returns the owning username if valid, else None. @claude"""
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


def rotate_refresh_token(token: str, db: sqlite3.Connection) -> tuple[str, str] | None:
    """
    Atomically revoke a valid refresh token and issue a replacement.
    Returns (username, new_refresh_token) on success, else None.

    @chatgpt
    """
    username = consume_refresh_token(token, db)
    if not username:
        return None

    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (_hash_refresh(token),),
    )
    if cur.rowcount == 0:
        db.commit()
        return None

    new_token = issue_refresh_token(username, db)
    return username, new_token


def revoke_refresh_token(token: str, db: sqlite3.Connection) -> bool:
    """Revoke a single refresh token. Returns True if revoked or already present, False if missing. @claude"""
    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (_hash_refresh(token),),
    )
    db.commit()
    return cur.rowcount > 0


def revoke_all_refresh_tokens(username: str, db: sqlite3.Connection) -> int:
    """Revoke every refresh token for a user (e.g. on password change). @claude"""
    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE username = ? AND revoked = 0",
        (username,),
    )
    db.commit()
    return cur.rowcount


# ── Password change ──────────────────────────────────────────────────────────


def change_password(
    username: str, current_password: str, new_password: str, db: sqlite3.Connection
) -> bool:
    """Change a user's password. Returns True on success, False if the current password is wrong. @claude"""
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
    # @claude Revoke every existing refresh token on password change (security).
    revoke_all_refresh_tokens(username, db)
    return True

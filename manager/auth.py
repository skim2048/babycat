"""
Babycat manager — credential verification, token issuing/rotation/revocation.

Access tokens are self-validating JWTs carrying a per-user epoch claim.
The router rejects tokens whose epoch is older than the account's current
epoch, so bumping the epoch here revokes every outstanding access token
immediately (FR-003, FR-005) without giving up self-validation (FR-001).

@claude
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from base64 import urlsafe_b64encode

from fastapi import HTTPException

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_EXPIRY = int(os.environ.get("JWT_EXPIRY", "600"))  # @claude 10m default (FR-001).
REFRESH_EXPIRY = int(os.environ.get("REFRESH_EXPIRY", str(60 * 60 * 24 * 30)))  # @claude 30d default (FR-002).

DEFAULT_USER = os.environ.get("DEFAULT_USER", "admin")
DEFAULT_PASS = os.environ.get("DEFAULT_PASS", "admin")

# @claude 10 failures -> 30-minute lockout (FR-007). Persisted in the users table.
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_SECONDS = 1800


def seed_default_user(db: sqlite3.Connection) -> None:
    row = db.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USER,)).fetchone()
    if not row:
        salt = secrets.token_hex(16)
        db.execute(
            "INSERT INTO users (username, password_hash, salt, password_changed) VALUES (?, ?, ?, 0)",
            (DEFAULT_USER, _hash_password(DEFAULT_PASS, salt), salt),
        )
        db.commit()


# ── Password ─────────────────────────────────────────────────────────────────


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def _verify_password(password: str, salt: str, pw_hash: str) -> bool:
    return hmac.compare_digest(_hash_password(password, salt), pw_hash)


# ── JWT (HMAC-SHA256; no external library) ───────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def create_token(username: str, epoch: int) -> str:
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY,
        "epoch": epoch,
    }).encode())
    signature = hmac.new(
        JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    return f"{header}.{payload}.{_b64url_encode(signature)}"


# ── Epoch (immediate revocation) ─────────────────────────────────────────────


def get_epoch(username: str, db: sqlite3.Connection) -> int | None:
    row = db.execute("SELECT token_epoch FROM users WHERE username = ?", (username,)).fetchone()
    return row["token_epoch"] if row else None


def bump_epoch(username: str, db: sqlite3.Connection) -> None:
    db.execute("UPDATE users SET token_epoch = token_epoch + 1 WHERE username = ?", (username,))
    db.commit()


# ── Login attempt limiter (DB-backed) ────────────────────────────────────────


def _check_lockout(row) -> int:
    remaining = row["locked_until"] - time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def _record_failure(username: str, db: sqlite3.Connection) -> None:
    row = db.execute(
        "SELECT failed_count FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        return  # @claude Unknown account: nothing to lock.
    count = row["failed_count"] + 1
    if count >= _LOCKOUT_THRESHOLD:
        db.execute(
            "UPDATE users SET failed_count = 0, locked_until = ? WHERE username = ?",
            (time.time() + _LOCKOUT_SECONDS, username),
        )
    else:
        db.execute("UPDATE users SET failed_count = ? WHERE username = ?", (count, username))
    db.commit()


# ── Authentication flow ──────────────────────────────────────────────────────


def authenticate(username: str, password: str, db: sqlite3.Connection) -> dict | None:
    """
    Authenticate a user.
      - On success, returns {"token", "must_change_password", "refresh_token"}.
      - On lockout, raises HTTPException(429).
      - On mismatch, returns None.
    """
    row = db.execute(
        "SELECT password_hash, salt, password_changed, token_epoch, failed_count, locked_until "
        "FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row:
        remaining = _check_lockout(row)
        if remaining > 0:
            raise HTTPException(
                status_code=429,
                detail=f"too many attempts, retry after {remaining}s",
                headers={"Retry-After": str(remaining)},
            )
    if not row or not _verify_password(password, row["salt"], row["password_hash"]):
        _record_failure(username, db)
        return None

    db.execute("UPDATE users SET failed_count = 0, locked_until = 0 WHERE username = ?", (username,))
    db.commit()
    return {
        "token": create_token(username, row["token_epoch"]),
        "must_change_password": not row["password_changed"],
        # remember_me selects the client session policy. Both policies still
        # need a server-side renewal token so the web app can support either
        # automatic renewal or an explicit "extend session" action.
        "refresh_token": issue_refresh_token(username, db),
    }


# ── Refresh Token ────────────────────────────────────────────────────────────


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(username: str, db: sqlite3.Connection) -> str:
    """Issue a new refresh token. Returns plaintext; the DB stores only the hash. @claude"""
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO refresh_tokens (token_hash, username, expires_at) VALUES (?, ?, ?)",
        (_hash_refresh(token), username, int(time.time()) + REFRESH_EXPIRY),
    )
    db.commit()
    return token


def rotate_refresh_token(token: str, db: sqlite3.Connection) -> tuple[str, str] | None:
    """Atomically revoke a valid refresh token and issue a replacement (FR-045)."""
    row = db.execute(
        "SELECT username, expires_at, revoked FROM refresh_tokens WHERE token_hash = ?",
        (_hash_refresh(token),),
    ).fetchone()
    if not row or row["revoked"] or row["expires_at"] < int(time.time()):
        return None
    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (_hash_refresh(token),),
    )
    if cur.rowcount == 0:
        db.commit()
        return None
    return row["username"], issue_refresh_token(row["username"], db)


def revoke_refresh_token(token: str, db: sqlite3.Connection) -> str | None:
    """Revoke a single refresh token; returns the owning username when found. @claude"""
    row = db.execute(
        "SELECT username FROM refresh_tokens WHERE token_hash = ?", (_hash_refresh(token),)
    ).fetchone()
    db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (_hash_refresh(token),),
    )
    db.commit()
    return row["username"] if row else None


def revoke_all_refresh_tokens(username: str, db: sqlite3.Connection) -> int:
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
    row = db.execute(
        "SELECT password_hash, salt FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row or not _verify_password(current_password, row["salt"], row["password_hash"]):
        return False
    new_salt = secrets.token_hex(16)
    db.execute(
        "UPDATE users SET password_hash = ?, salt = ?, password_changed = 1 WHERE username = ?",
        (_hash_password(new_password, new_salt), new_salt, username),
    )
    db.commit()
    # @claude FR-005: drop every existing token — refresh via revocation,
    # @claude access via epoch bump (the router compares epochs per request).
    revoke_all_refresh_tokens(username, db)
    bump_epoch(username, db)
    return True

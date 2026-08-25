"""
Babycat router — accounts, tokens, and request authentication.

Issuing and verifying live in one process (SDD §4.1): access tokens are
self-validating JWTs carrying a per-user epoch claim, and the revocation
check is a read of the router's own account database — no internal HTTP.
Bumping the epoch on login/logout/password change revokes every
outstanding access token immediately (FR-003, FR-005, FR-047) without
giving up self-validation (FR-001).

@claude
"""

import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sqlite3
import threading
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import Depends, HTTPException, Request

from database import get_db

# @claude Generated once with a CSPRNG and kept next to the account database
# @claude (0600), never taken from the environment or the repository (NFR-013).
# @claude Like the gateway's CA, sharing it across devices is a file copy.
_SECRET_PATH = pathlib.Path(os.environ.get("DB_PATH", "/data/db/router.db")).with_name("jwt_secret")


def _load_or_create_secret() -> str:
    try:
        secret = _SECRET_PATH.read_text().strip()
        if secret:
            return secret
    except FileNotFoundError:
        pass
    _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    fd = os.open(_SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secret)
    return secret


JWT_SECRET = _load_or_create_secret()
JWT_EXPIRY = int(os.environ.get("JWT_EXPIRY", "600"))  # @claude 10m default (FR-001).
REFRESH_EXPIRY = int(os.environ.get("REFRESH_EXPIRY", str(60 * 60 * 24 * 30)))  # @claude 30d default (FR-002).

DEFAULT_USER = os.environ.get("DEFAULT_USER", "admin")
DEFAULT_PASS = os.environ.get("DEFAULT_PASS", "admin")

# @claude 10 failures -> 30-minute lockout (FR-007). Persisted in the users table.
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_SECONDS = 1800
# @claude WHEP session rows are deleted on client DELETE or replacement; rows
# @claude MediaMTX closed on its own (ICE timeout) are aged out after this.
_WHEP_SESSION_MAX_AGE = 24 * 3600

# @claude Serializes session-mutating operations: login replacement, refresh
# @claude rotation, logout, password change (SDD §6.2). Without it, a rotation
# @claude interleaved with a login's revoke-all could insert its new refresh
# @claude token after the sweep and mint an access token with the post-bump
# @claude epoch — a replaced session surviving the replacement (FR-047).
SESSION_LOCK = threading.Lock()


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


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return urlsafe_b64decode(s + "=" * padding)


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


# ── Epoch (immediate revocation) ─────────────────────────────────────────────


def get_epoch(username: str, db: sqlite3.Connection) -> int | None:
    row = db.execute("SELECT token_epoch FROM users WHERE username = ?", (username,)).fetchone()
    return row["token_epoch"] if row else None


def bump_epoch(username: str, db: sqlite3.Connection) -> None:
    db.execute("UPDATE users SET token_epoch = token_epoch + 1 WHERE username = ?", (username,))
    db.commit()


# ── Request authentication (FastAPI dependency) ──────────────────────────────


def require_auth(request: Request, db: sqlite3.Connection = Depends(get_db)) -> dict:
    """Validates Authorization: Bearer <token>, or ?token=<token> as a fallback
    for clients that cannot set headers (EventSource, <video src>, HLS).
    Signature/expiry are self-validated; the epoch claim is compared against
    the account database so revocation is immediate (SDD §6.2).

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
    if payload.get("epoch", -1) != get_epoch(payload.get("sub", ""), db):
        raise HTTPException(status_code=401, detail="token revoked")
    return payload


# ── Login attempt limiter (DB-backed) ────────────────────────────────────────


def _check_lockout(row) -> int:
    remaining = row["locked_until"] - time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def _record_failure(username: str, db: sqlite3.Connection) -> int:
    """Count one failure. Returns the lockout length in seconds when this
    failure reached the threshold (FR-007: the 10th failure is already
    refused with 429), else 0."""
    row = db.execute(
        "SELECT failed_count FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        return 0  # @claude Unknown account: nothing to lock.
    count = row["failed_count"] + 1
    if count >= _LOCKOUT_THRESHOLD:
        db.execute(
            "UPDATE users SET failed_count = 0, locked_until = ? WHERE username = ?",
            (time.time() + _LOCKOUT_SECONDS, username),
        )
        db.commit()
        return _LOCKOUT_SECONDS
    db.execute("UPDATE users SET failed_count = ? WHERE username = ?", (count, username))
    db.commit()
    return 0


# ── Authentication flow ──────────────────────────────────────────────────────


def authenticate(
    username: str, password: str, db: sqlite3.Connection, remember_me: bool = False
) -> dict | None:
    """
    Authenticate a user.
      - On success, returns {"token", "must_change_password", "refresh_token"}.
        The refresh token is issued only when the login asked to be kept
        (remember_me, FR-002); otherwise it is None and the session ends with
        the access token. Success replaces the account's existing session
        (FR-047): all prior tokens are dead by the time the new ones are issued.
      - On lockout (including the failure that triggers it), raises
        HTTPException(429).
      - On mismatch, returns None.
    """
    purge_expired(db)
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
        locked_for = _record_failure(username, db)
        if locked_for:
            raise HTTPException(
                status_code=429,
                detail=f"too many attempts, retry after {locked_for}s",
                headers={"Retry-After": str(locked_for)},
            )
        return None

    db.execute("UPDATE users SET failed_count = 0, locked_until = 0 WHERE username = ?", (username,))
    db.commit()
    # @claude FR-047: a new login replaces the account's existing session —
    # @claude refresh tokens via revocation, access tokens via the epoch bump.
    # @claude The new access token must carry the post-bump epoch.
    with SESSION_LOCK:
        revoke_all_refresh_tokens(username, db)
        bump_epoch(username, db)
        return {
            "token": create_token(username, get_epoch(username, db) or 0),
            "must_change_password": not row["password_changed"],
            "refresh_token": issue_refresh_token(username, db) if remember_me else None,
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


def purge_expired(db: sqlite3.Connection) -> None:
    """Lazy deletion on access (SDD §5.5): expired or revoked refresh tokens,
    and WHEP session records older than a day — a session MediaMTX closed on
    ICE timeout is never reported back, so its row is aged out here. @claude"""
    now = int(time.time())
    db.execute("DELETE FROM refresh_tokens WHERE expires_at < ? OR revoked = 1", (now,))
    db.execute("DELETE FROM whep_sessions WHERE created_at < ?", (now - _WHEP_SESSION_MAX_AGE,))
    db.commit()


def rotate_refresh_token(token: str, db: sqlite3.Connection) -> tuple[str, str] | None:
    """Atomically revoke a valid refresh token and issue a replacement (FR-045)."""
    purge_expired(db)
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
    """Revoke a single refresh token; returns the owning username only when an
    active token was actually revoked. An already-revoked token belongs to a
    replaced session — letting it identify the user would bump the epoch and
    kill the replacing session (FR-047). @claude"""
    row = db.execute(
        "SELECT username FROM refresh_tokens WHERE token_hash = ?", (_hash_refresh(token),)
    ).fetchone()
    cur = db.execute(
        "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND revoked = 0",
        (_hash_refresh(token),),
    )
    db.commit()
    return row["username"] if row and cur.rowcount > 0 else None


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
    # @claude access via epoch bump (require_auth compares epochs per request).
    with SESSION_LOCK:
        revoke_all_refresh_tokens(username, db)
        bump_epoch(username, db)
    return True

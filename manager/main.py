"""
Babycat manager — internal authentication service.

Internal only: no port is published; the router is the sole caller and
performs external authentication itself (SDD §6.3). Response shapes match
the external contract so the router can relay them unchanged.

@claude
"""

import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from auth import (
    JWT_EXPIRY,
    REFRESH_EXPIRY,
    authenticate,
    bump_epoch,
    change_password,
    create_token,
    get_epoch,
    revoke_refresh_token,
    rotate_refresh_token,
    seed_default_user,
)
from database import DB_PATH, get_db, init_db


class LoginIn(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class TokenOut(BaseModel):
    token: str
    expires_in: int
    must_change_password: bool = False
    refresh_token: Optional[str] = None
    refresh_expires_in: Optional[int] = None


class RefreshIn(BaseModel):
    refresh_token: str


class RefreshOut(BaseModel):
    token: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int


class LogoutIn(BaseModel):
    refresh_token: Optional[str] = None
    username: Optional[str] = None


class ChangePasswordIn(BaseModel):
    username: str
    current_password: str
    new_password: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        seed_default_user(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Babycat manager", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/internal/login", response_model=TokenOut)
def login(body: LoginIn, db: sqlite3.Connection = Depends(get_db)):
    result = authenticate(body.username, body.password, db)
    if not result:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenOut(
        token=result["token"],
        expires_in=JWT_EXPIRY,
        must_change_password=result["must_change_password"],
        refresh_token=result["refresh_token"],
        refresh_expires_in=REFRESH_EXPIRY,
    )


@app.post("/internal/refresh", response_model=RefreshOut)
def refresh(body: RefreshIn, db: sqlite3.Connection = Depends(get_db)):
    rotated = rotate_refresh_token(body.refresh_token, db)
    if not rotated:
        raise HTTPException(status_code=401, detail="invalid or expired refresh token")
    username, new_refresh_token = rotated
    epoch = get_epoch(username, db) or 0
    return RefreshOut(
        token=create_token(username, epoch),
        expires_in=JWT_EXPIRY,
        refresh_token=new_refresh_token,
        refresh_expires_in=REFRESH_EXPIRY,
    )


@app.post("/internal/logout")
def logout(body: LogoutIn, db: sqlite3.Connection = Depends(get_db)):
    """
    Revoke the refresh token and bump the epoch so outstanding access
    tokens die with it (FR-003). The username comes from the refresh
    token when present, else from the router-verified access token.
    """
    username = None
    if body.refresh_token:
        username = revoke_refresh_token(body.refresh_token, db)
    if not username:
        username = body.username
    if username:
        bump_epoch(username, db)
    return {"ok": True}


@app.post("/internal/change-password")
def internal_change_password(body: ChangePasswordIn, db: sqlite3.Connection = Depends(get_db)):
    ok = change_password(body.username, body.current_password, body.new_password, db)
    if not ok:
        raise HTTPException(status_code=400, detail="current password is incorrect")
    return {"ok": True}


@app.get("/internal/epoch")
def epoch(username: str, db: sqlite3.Connection = Depends(get_db)):
    value = get_epoch(username, db)
    if value is None:
        raise HTTPException(status_code=404, detail="unknown user")
    return {"username": username, "epoch": value}

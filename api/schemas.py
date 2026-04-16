"""Babycat — Pydantic request/response schemas."""

from pydantic import BaseModel
from typing import Optional


# ── Auth ────────────────────────────────────────────────────────────────────

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


class LogoutIn(BaseModel):
    refresh_token: Optional[str] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


# ── Camera Profile ──────────────────────────────────────────────────────────

class CameraProfileIn(BaseModel):
    ip: str
    username: str
    password: str
    rtsp_port: Optional[int] = None
    onvif_port: Optional[int] = None
    stream_path: Optional[str] = None
    stream_protocol: Optional[str] = None


class CameraProfileOut(BaseModel):
    configured: bool
    ip: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    rtsp_port: Optional[int] = None
    onvif_port: Optional[int] = None
    stream_path: Optional[str] = None
    stream_protocol: Optional[str] = None
    ptz_home: Optional[str] = None


class ApplyResultOut(BaseModel):
    ok: bool
    error: Optional[str] = None


# ── Clip ─────────────────────────────────────────────────────────────────────

class ClipOut(BaseModel):
    name: str
    size: int
    created_at: str
    timestamp: Optional[int] = None
    keywords: list[str] = []
    vlm_text: Optional[str] = None


class ClipListOut(BaseModel):
    clips: list[ClipOut]
    total: int


class ClipDeleteIn(BaseModel):
    names: list[str]


class DeletedOut(BaseModel):
    deleted: int


# ── Event ────────────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    trigger: str
    clip_name: Optional[str] = None


class EventOut(BaseModel):
    id: int
    trigger: str
    clip_name: Optional[str]
    created_at: str


class EventListOut(BaseModel):
    events: list[EventOut]
    total: int


# ── Device ───────────────────────────────────────────────────────────────────

class DeviceIn(BaseModel):
    fcm_token: str
    label: Optional[str] = None


class DeviceOut(BaseModel):
    id: int
    fcm_token: str
    label: Optional[str]
    registered_at: str


class DeviceListOut(BaseModel):
    devices: list[DeviceOut]

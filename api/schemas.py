"""Babycat — Pydantic request/response schemas."""

from pydantic import BaseModel
from typing import Optional


# ── Auth ────────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    token: str
    expires_in: int
    must_change_password: bool = False


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


# ── Clip ─────────────────────────────────────────────────────────────────────

class ClipOut(BaseModel):
    name: str
    size: int
    created_at: str
    camera: str


class ClipListOut(BaseModel):
    clips: list[ClipOut]
    total: int


class ClipDeleteIn(BaseModel):
    names: list[str]
    camera: str | None = None


class CameraListOut(BaseModel):
    """클립이 존재하는 카메라 이름 목록."""
    cameras: list[str]


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

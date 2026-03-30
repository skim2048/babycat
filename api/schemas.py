"""Babycat — Pydantic request/response schemas."""

from pydantic import BaseModel
from typing import Optional


# ── Clip ─────────────────────────────────────────────────────────────────────

class ClipOut(BaseModel):
    name: str
    size: int
    created_at: str


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

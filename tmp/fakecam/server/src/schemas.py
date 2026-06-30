"""Pydantic models for the fakecam control API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


Resolution = Literal["360p", "720p", "1080p"]
Fps = Literal[10, 15, 20, 25, 30, 60]
BitrateMbps = Literal[1, 2, 4, 8]
AudioMode = Literal["drop", "keep"]
RepeatMode = Literal["off", "all", "one"]


class FileNode(BaseModel):
    type: Literal["file"] = "file"
    name: str
    path: str
    size_bytes: int


class DirectoryNode(BaseModel):
    type: Literal["dir"] = "dir"
    name: str
    children: list["DirectoryNode | FileNode"] = Field(default_factory=list)


DirectoryNode.model_rebuild()


class LibraryResponse(BaseModel):
    tree: DirectoryNode


class Settings(BaseModel):
    auth_user: str = Field(default="admin", min_length=1, max_length=64)
    auth_password: str = Field(default="admin", min_length=1, max_length=128)
    port: int = Field(default=554, ge=1, le=65535)
    rtsp_path: str = Field(default="/live", pattern=r"^/[A-Za-z0-9_\-/]*$")
    resolution: Resolution = "720p"
    fps: Fps = 30
    bitrate_mbps: BitrateMbps = 2
    audio: AudioMode = "drop"


class SettingsUpdate(BaseModel):
    auth_user: Optional[str] = Field(default=None, min_length=1, max_length=64)
    auth_password: Optional[str] = Field(default=None, min_length=1, max_length=128)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    rtsp_path: Optional[str] = Field(default=None, pattern=r"^/[A-Za-z0-9_\-/]*$")
    resolution: Optional[Resolution] = None
    fps: Optional[Fps] = None
    bitrate_mbps: Optional[BitrateMbps] = None
    audio: Optional[AudioMode] = None


class PlaylistItem(BaseModel):
    path: str
    name: str


class PlaylistState(BaseModel):
    items: list[PlaylistItem] = Field(default_factory=list)
    current_path: Optional[str] = None
    is_playing: bool = False


class PlaybackMode(BaseModel):
    shuffle: bool = False
    repeat: RepeatMode = "off"


class PlaylistMutation(BaseModel):
    paths: list[str]


class PlaybackModeUpdate(BaseModel):
    shuffle: Optional[bool] = None
    repeat: Optional[RepeatMode] = None

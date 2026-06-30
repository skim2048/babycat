"""FastAPI app builder.

Phase 2 surface:
  - GET  /api/library            tree of mp4 files under VIDEOS_DIR
  - GET  /api/settings           current settings snapshot
  - PUT  /api/settings           partial update; persists to disk
  - GET  /api/playlist           current playlist + playback flag
  - POST /api/playlist/add       add by paths (duplicates ignored)
  - POST /api/playlist/remove    remove by paths
  - POST /api/playback/play      start from first item
  - POST /api/playback/stop      stop and reset to head
  - PUT  /api/playback/mode      update shuffle/repeat
  - GET  /api/events             SSE: playlist / mode / settings updates

Mutations that require an idle RTSP session (transport-level settings,
playlist add/remove during playback) return 409 Conflict.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import library
from .events import EventBus
from .playback import PlaybackController
from .playlist import PlaylistStore
from .rtsp_server import RtspServer
from .schemas import (
    LibraryResponse,
    PlaybackMode,
    PlaybackModeUpdate,
    PlaylistMutation,
    PlaylistState,
    Settings,
    SettingsUpdate,
)
from .settings import SettingsStore


log = logging.getLogger(__name__)

TRANSPORT_FIELDS = ("port", "rtsp_path", "auth_user", "auth_password")


def build_app(
    *,
    videos_dir: str,
    settings_store: SettingsStore,
    rtsp_server: RtspServer,
    playlist: PlaylistStore,
    playback: PlaybackController,
    event_bus: EventBus,
) -> FastAPI:
    app = FastAPI(title="fakecam", version="0.2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _capture_loop() -> None:
        event_bus.attach_loop(asyncio.get_running_loop())

    # ── library ──────────────────────────────────────────────────────────────

    @app.get("/api/library", response_model=LibraryResponse)
    def get_library() -> LibraryResponse:
        return LibraryResponse(tree=library.scan(videos_dir))

    # ── settings ─────────────────────────────────────────────────────────────

    @app.get("/api/settings", response_model=Settings)
    def get_settings() -> Settings:
        return settings_store.get()

    @app.put("/api/settings", response_model=Settings)
    def put_settings(patch: SettingsUpdate) -> Settings:
        if playback.is_playing():
            patch_data = patch.model_dump(exclude_none=True)
            if patch_data:
                # @claude Any change while playing is rejected; the UI is expected to
                # @claude stop playback first per the 사용자 사양.
                raise HTTPException(
                    status_code=409,
                    detail="settings cannot change while playing; stop first",
                )
        return settings_store.update(patch)

    # ── playlist ─────────────────────────────────────────────────────────────

    @app.get("/api/playlist", response_model=PlaylistState)
    def get_playlist() -> PlaylistState:
        return playback.state()

    @app.post("/api/playlist/add", response_model=PlaylistState)
    def add_to_playlist(body: PlaylistMutation) -> PlaylistState:
        if playback.is_playing():
            raise HTTPException(status_code=409, detail="cannot mutate playlist while playing")
        playlist.add(body.paths, videos_dir)
        return playback.state()

    @app.post("/api/playlist/remove", response_model=PlaylistState)
    def remove_from_playlist(body: PlaylistMutation) -> PlaylistState:
        if playback.is_playing():
            raise HTTPException(status_code=409, detail="cannot mutate playlist while playing")
        playlist.remove(body.paths)
        return playback.state()

    # ── playback ─────────────────────────────────────────────────────────────

    @app.post("/api/playback/play", response_model=PlaylistState)
    def play() -> PlaylistState:
        playback.play()
        return playback.state()

    @app.post("/api/playback/stop", response_model=PlaylistState)
    def stop() -> PlaylistState:
        playback.stop()
        return playback.state()

    @app.put("/api/playback/mode", response_model=PlaybackMode)
    def put_mode(body: PlaybackModeUpdate) -> PlaybackMode:
        return playback.set_mode(shuffle=body.shuffle, repeat=body.repeat)

    # ── SSE ──────────────────────────────────────────────────────────────────

    @app.get("/api/events")
    async def events(request: Request):
        async def gen():
            q = event_bus.subscribe()
            try:
                yield _format({"type": "library", "tree": library.scan(videos_dir).model_dump()})
                yield _format({"type": "playlist", "playlist": playback.state().model_dump()})
                yield _format({"type": "mode", "mode": playback.mode().model_dump()})
                yield _format({"type": "settings", "settings": settings_store.get().model_dump()})
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield _format(event)
                    except asyncio.TimeoutError:
                        yield b": keepalive\n\n"
            finally:
                event_bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def _format(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()

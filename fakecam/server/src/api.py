"""FastAPI app builder.

Phase 1 surface:
  - GET  /api/library          tree of mp4 files under VIDEOS_DIR
  - GET  /api/settings         current settings snapshot
  - PUT  /api/settings         partial update; persists to disk
  - POST /api/_debug/play      Phase 1 only: { "path": "<rel>" } → stream
  - POST /api/_debug/stop      Phase 1 only: clear current stream

The _debug endpoints exist so VLC can verify single-file RTSP output
before the playlist + playback module land in Phase 2. They will be
removed when the proper /api/playback endpoints take over.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import library
from .rtsp_server import RtspServer
from .schemas import (
    LibraryResponse,
    PlaylistMutation,
    Settings,
    SettingsUpdate,
)
from .settings import SettingsStore


log = logging.getLogger(__name__)


def build_app(
    *,
    videos_dir: str,
    settings_store: SettingsStore,
    rtsp_server: RtspServer,
) -> FastAPI:
    app = FastAPI(title="fakecam", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/library", response_model=LibraryResponse)
    def get_library() -> LibraryResponse:
        return LibraryResponse(tree=library.scan(videos_dir))

    @app.get("/api/settings", response_model=Settings)
    def get_settings() -> Settings:
        return settings_store.get()

    @app.put("/api/settings", response_model=Settings)
    def put_settings(patch: SettingsUpdate) -> Settings:
        return settings_store.update(patch)

    @app.post("/api/_debug/play")
    def debug_play(body: PlaylistMutation) -> dict:
        if not body.paths:
            raise HTTPException(status_code=400, detail="paths must not be empty")
        rel = body.paths[0]
        abs_path = library.resolve(videos_dir, rel)
        if abs_path is None:
            raise HTTPException(status_code=404, detail=f"not found or not an mp4: {rel}")
        rtsp_server.set_current(abs_path)
        return {"ok": True, "current": rel}

    @app.post("/api/_debug/stop")
    def debug_stop() -> dict:
        rtsp_server.clear_current()
        return {"ok": True}

    return app

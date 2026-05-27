"""Playback state machine.

Owns the cursor through the playlist, shuffle/repeat modes, and the
play/stop flag. Mutations call into the RTSP server to set or clear
the currently-streamed file. State changes are broadcast to listeners
so the SSE channel can forward them to web clients.

The controller is the single thread-safe gateway for all playback
intent — both HTTP handlers and the GStreamer bus (on natural EOS)
go through these methods.
"""

from __future__ import annotations

import logging
import random
import threading
from pathlib import Path
from typing import Callable

from . import library
from .playlist import PlaylistStore
from .rtsp_server import RtspServer
from .schemas import PlaybackMode, PlaylistItem, PlaylistState, RepeatMode


log = logging.getLogger(__name__)

Listener = Callable[[PlaylistState, PlaybackMode], None]


class PlaybackController:
    def __init__(
        self,
        playlist: PlaylistStore,
        rtsp_server: RtspServer,
        videos_dir: str | Path,
    ):
        self._playlist = playlist
        self._rtsp_server = rtsp_server
        self._videos_dir = Path(videos_dir)
        self._lock = threading.Lock()
        self._is_playing = False
        self._shuffle = False
        self._repeat: RepeatMode = "off"
        self._cursor = 0
        self._order: list[int] | None = None
        self._listeners: list[Listener] = []
        playlist.subscribe(self._on_playlist_changed)

    # ── public reads ─────────────────────────────────────────────────────────

    def state(self) -> PlaylistState:
        items = self._playlist.get()
        with self._lock:
            return PlaylistState(
                items=items,
                current_path=self._current_path_locked(items),
                is_playing=self._is_playing,
            )

    def mode(self) -> PlaybackMode:
        with self._lock:
            return PlaybackMode(shuffle=self._shuffle, repeat=self._repeat)

    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    # ── public mutations ─────────────────────────────────────────────────────

    def play(self) -> bool:
        with self._lock:
            items = self._playlist.get()
            if not items:
                return False
            self._cursor = 0
            self._order = self._fresh_order(len(items))
            self._is_playing = True
            self._apply_current_locked(items)
        self._broadcast()
        return True

    def stop(self) -> None:
        with self._lock:
            self._set_stopped_locked()
        self._broadcast()

    def next(self) -> None:
        self._step(+1)

    def prev(self) -> None:
        self._step(-1)

    def on_natural_eos(self) -> None:
        """Hook invoked by the RTSP layer when the current file reaches EOS."""
        if not self.is_playing():
            return
        self._step(+1)

    def set_mode(
        self,
        shuffle: bool | None = None,
        repeat: RepeatMode | None = None,
    ) -> PlaybackMode:
        with self._lock:
            items = self._playlist.get()
            if shuffle is not None and shuffle != self._shuffle:
                current_idx = self._current_index_locked(items)
                self._shuffle = shuffle
                if shuffle:
                    indices = list(range(len(items)))
                    if current_idx is not None and current_idx in indices:
                        indices.remove(current_idx)
                        random.shuffle(indices)
                        self._order = [current_idx] + indices
                    else:
                        random.shuffle(indices)
                        self._order = indices
                    self._cursor = 0
                else:
                    self._order = list(range(len(items)))
                    self._cursor = current_idx if current_idx is not None else 0
            if repeat is not None:
                self._repeat = repeat
        self._broadcast()
        return self.mode()

    # ── internals ────────────────────────────────────────────────────────────

    def _step(self, delta: int) -> None:
        with self._lock:
            if not self._is_playing:
                return
            items = self._playlist.get()
            if not items:
                self._set_stopped_locked()
            elif self._repeat == "one":
                self._apply_current_locked(items)
            else:
                order = self._ensure_order_locked(items)
                new_cursor = self._cursor + delta
                if new_cursor >= len(order):
                    if self._repeat == "all":
                        new_cursor = 0
                        if self._shuffle:
                            self._order = self._fresh_order(len(items))
                    else:
                        self._set_stopped_locked()
                        new_cursor = None
                elif new_cursor < 0:
                    new_cursor = len(order) - 1 if self._repeat == "all" else 0
                if new_cursor is not None:
                    self._cursor = new_cursor
                    self._apply_current_locked(items)
        self._broadcast()

    def _on_playlist_changed(self, items: list[PlaylistItem]) -> None:
        broadcast = False
        with self._lock:
            if not self._is_playing:
                return
            broadcast = True
            if not items:
                self._set_stopped_locked()
            else:
                current = self._current_path_locked(items)
                order = self._fresh_order(len(items))
                self._order = order
                if current is None:
                    self._cursor = 0
                else:
                    self._cursor = next(
                        (i for i, idx in enumerate(order) if items[idx].path == current),
                        0,
                    )
                self._apply_current_locked(items)
        if broadcast:
            self._broadcast()

    def _fresh_order(self, n: int) -> list[int]:
        order = list(range(n))
        if self._shuffle:
            random.shuffle(order)
        return order

    def _ensure_order_locked(self, items: list[PlaylistItem]) -> list[int]:
        if self._order is None or len(self._order) != len(items):
            self._order = self._fresh_order(len(items))
        return self._order

    def _current_index_locked(self, items: list[PlaylistItem]) -> int | None:
        if not self._is_playing or not items:
            return None
        order = self._order or list(range(len(items)))
        if not (0 <= self._cursor < len(order)):
            return None
        idx = order[self._cursor]
        return idx if 0 <= idx < len(items) else None

    def _current_path_locked(self, items: list[PlaylistItem]) -> str | None:
        idx = self._current_index_locked(items)
        return items[idx].path if idx is not None else None

    def _apply_current_locked(self, items: list[PlaylistItem]) -> None:
        idx = self._current_index_locked(items)
        if idx is None:
            self._rtsp_server.clear_current()
            return
        abs_path = library.resolve(self._videos_dir, items[idx].path)
        if abs_path is None:
            log.warning("playback: file disappeared, stopping: %s", items[idx].path)
            self._set_stopped_locked()
            return
        self._rtsp_server.set_current(abs_path)

    def _set_stopped_locked(self) -> None:
        self._is_playing = False
        self._cursor = 0
        self._order = None
        self._rtsp_server.clear_current()

    def _broadcast(self) -> None:
        snapshot = self.state()
        mode = self.mode()
        for cb in list(self._listeners):
            try:
                cb(snapshot, mode)
            except Exception:
                log.exception("playback listener failed")

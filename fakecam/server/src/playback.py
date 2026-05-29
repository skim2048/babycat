"""Playback state machine.

Drives the concat-based RTSP pipeline:

  - `play()` records the first file via `RtspServer.set_initial`, which
    determines what gets parsed when a client first connects.
  - On `on_post_configure`, called once per fresh media construction,
    the controller enqueues the natural lookahead so concat has
    something to switch to when the initial file ends.
  - On `on_advance`, called every time concat changes its active pad,
    the cursor is promoted to the queued cursor and a new lookahead
    is enqueued.
  - `on_exhausted` fires when the pipeline as a whole reaches EOS
    (no lookahead was queued, e.g. repeat=off at the end of the
    playlist). It performs a clean stop.

Mutations under `_lock`; broadcasts run outside the lock so listeners
can call back without risk of deadlock.
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
        self._queued_cursor: int | None = None
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
        items = self._playlist.get()
        if not items:
            return False
        first_path: Path | None
        with self._lock:
            if self._is_playing:
                return True
            self._cursor = 0
            self._queued_cursor = None
            self._order = self._fresh_order(len(items))
            self._is_playing = True
            first_path = self._resolve_at(items, self._order[0])
        self._rtsp_server.set_initial(first_path)
        self._broadcast()
        return True

    def stop(self) -> None:
        with self._lock:
            self._set_stopped_locked()
        self._rtsp_server.set_initial(None)
        self._rtsp_server.stop_streaming()
        self._broadcast()

    def set_mode(
        self,
        shuffle: bool | None = None,
        repeat: RepeatMode | None = None,
    ) -> PlaybackMode:
        items = self._playlist.get()
        new_lookahead_path: Path | None = None
        broadcast = False
        with self._lock:
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
                self._queued_cursor = None
                broadcast = True
            if repeat is not None and repeat != self._repeat:
                self._repeat = repeat
                self._queued_cursor = None
                broadcast = True
            if self._is_playing and self._queued_cursor is None:
                lookahead = self._lookahead_locked(items)
                if lookahead is not None:
                    self._queued_cursor = lookahead
                    new_lookahead_path = self._resolve_at(items, self._order[lookahead])
        if self._is_playing:
            self._rtsp_server.enqueue_next(new_lookahead_path)
        if broadcast:
            self._broadcast()
        return self.mode()

    # ── hooks from RtspServer (GLib thread) ──────────────────────────────────

    def on_post_configure(self) -> None:
        """Called once per fresh media. Pre-queue the lookahead."""
        items = self._playlist.get()
        path: Path | None = None
        with self._lock:
            if not self._is_playing or not items:
                return
            lookahead = self._lookahead_locked(items)
            if lookahead is not None:
                self._queued_cursor = lookahead
                path = self._resolve_at(items, self._order[lookahead])
        if path is not None:
            self._rtsp_server.enqueue_next(path)

    def on_advance(self) -> None:
        """Called when concat advanced to the previously-queued input."""
        items = self._playlist.get()
        new_initial: Path | None = None
        new_path: Path | None = None
        broadcast = False
        with self._lock:
            if not self._is_playing:
                return
            if self._queued_cursor is None:
                # @claude Advance without a queued cursor — likely the result of
                # @claude a settings change race. Stay put logically.
                return
            self._cursor = self._queued_cursor
            self._queued_cursor = None
            broadcast = True
            # @claude Sync the RTSP factory's initial source so that if VLC
            # @claude disconnects and reconnects mid-playlist, the freshly-built
            # @claude media resumes from the same logical position rather than
            # @claude restarting from the original first item.
            new_initial = self._resolve_at(items, self._order[self._cursor])
            lookahead = self._lookahead_locked(items)
            if lookahead is not None:
                self._queued_cursor = lookahead
                new_path = self._resolve_at(items, self._order[lookahead])
        if new_initial is not None:
            self._rtsp_server.set_initial(new_initial)
        if new_path is not None:
            self._rtsp_server.enqueue_next(new_path)
        if broadcast:
            self._broadcast()

    def on_exhausted(self) -> None:
        """Pipeline EOS — concat ran out of inputs."""
        with self._lock:
            if not self._is_playing:
                return
            self._set_stopped_locked()
        self._rtsp_server.set_initial(None)
        self._broadcast()

    # ── internals ────────────────────────────────────────────────────────────

    def _lookahead_locked(self, items: list[PlaylistItem]) -> int | None:
        """Compute the cursor of the natural next item (no user override)."""
        if not items:
            return None
        order = self._ensure_order_locked(items)
        if self._repeat == "one":
            return self._cursor
        next_cursor = self._cursor + 1
        if next_cursor >= len(order):
            if self._repeat == "all":
                # @claude Wrap reuses the existing shuffle order; the order is
                # @claude only regenerated on the play()→stop()→play() cycle
                # @claude or on a shuffle toggle via set_mode.
                return 0
            return None
        return next_cursor

    def _on_playlist_changed(self, items: list[PlaylistItem]) -> None:
        # Currently mutations are blocked during playback (409 in api.py), so
        # this only fires while stopped. No action required.
        pass

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

    def _resolve_at(self, items: list[PlaylistItem], idx: int) -> Path | None:
        if not (0 <= idx < len(items)):
            return None
        return library.resolve(self._videos_dir, items[idx].path)

    def _set_stopped_locked(self) -> None:
        self._is_playing = False
        self._cursor = 0
        self._queued_cursor = None
        self._order = None

    def _broadcast(self) -> None:
        snapshot = self.state()
        mode = self.mode()
        for cb in list(self._listeners):
            try:
                cb(snapshot, mode)
            except Exception:
                log.exception("playback listener failed")

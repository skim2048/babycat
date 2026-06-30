"""Playlist store.

A name-sorted set of mp4 files. The store keeps no knowledge of
playback state — that lives in `playback.PlaybackController`. The
playback module reads from this store and is notified on mutations
through the listener callback.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from . import library
from .schemas import PlaylistItem


class PlaylistStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: list[PlaylistItem] = []
        self._listeners: list[Callable[[list[PlaylistItem]], None]] = []

    def get(self) -> list[PlaylistItem]:
        with self._lock:
            return list(self._items)

    def add(self, paths: list[str], videos_dir: str | Path) -> list[PlaylistItem]:
        with self._lock:
            existing = {item.path for item in self._items}
            for rel in paths:
                if rel in existing:
                    continue
                if library.resolve(videos_dir, rel) is None:
                    continue
                self._items.append(PlaylistItem(path=rel, name=Path(rel).name))
                existing.add(rel)
            self._items.sort(key=lambda it: it.name.lower())
            snapshot = list(self._items)
        self._notify(snapshot)
        return snapshot

    def remove(self, paths: list[str]) -> list[PlaylistItem]:
        targets = set(paths)
        with self._lock:
            self._items = [it for it in self._items if it.path not in targets]
            snapshot = list(self._items)
        self._notify(snapshot)
        return snapshot

    def index_of(self, path: str) -> int | None:
        with self._lock:
            for i, item in enumerate(self._items):
                if item.path == path:
                    return i
        return None

    def at(self, index: int) -> PlaylistItem | None:
        with self._lock:
            if 0 <= index < len(self._items):
                return self._items[index]
            return None

    def size(self) -> int:
        with self._lock:
            return len(self._items)

    def subscribe(self, callback: Callable[[list[PlaylistItem]], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, snapshot: list[PlaylistItem]) -> None:
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:  # noqa: BLE001
                pass

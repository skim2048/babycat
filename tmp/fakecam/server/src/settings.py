"""Settings store with disk persistence and observer callbacks.

State path is configured via the STATE_PATH environment variable; if the
file is missing or unreadable the defaults from `schemas.Settings` are
used and a fresh file is written on the first update.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable

from .schemas import Settings, SettingsUpdate


log = logging.getLogger(__name__)


class SettingsStore:
    def __init__(self, state_path: str | os.PathLike):
        self._path = Path(state_path)
        self._lock = threading.Lock()
        self._settings = self._load()
        self._listeners: list[Callable[[Settings], None]] = []

    def _load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("settings load failed (%s); using defaults", e)
            return Settings()
        try:
            return Settings.model_validate(data)
        except Exception as e:
            log.warning("settings validation failed (%s); using defaults", e)
            return Settings()

    def _persist_locked(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._settings.model_dump(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError as e:
            log.error("settings persist failed: %s", e)
            try:
                tmp.unlink()
            except OSError:
                pass

    def get(self) -> Settings:
        with self._lock:
            return self._settings.model_copy()

    def update(self, patch: SettingsUpdate) -> Settings:
        with self._lock:
            data = self._settings.model_dump()
            data.update({k: v for k, v in patch.model_dump().items() if v is not None})
            self._settings = Settings.model_validate(data)
            self._persist_locked()
            snapshot = self._settings.model_copy()
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:
                log.exception("settings listener failed")
        return snapshot

    def subscribe(self, callback: Callable[[Settings], None]) -> None:
        self._listeners.append(callback)

"""Filesystem watcher for the videos/ directory.

Runs a daemon thread that blocks on `watchfiles.watch` (inotify on
Linux) and invokes the supplied callback whenever anything changes
under the watched root. `watchfiles` already coalesces bursts of
events into batches, so the callback fires once per debounced change
rather than once per inotify event.

The callback is expected to be cheap (e.g. a re-scan plus an SSE
publish); any heavier work should be dispatched elsewhere.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from watchfiles import watch


log = logging.getLogger(__name__)


class LibraryWatcher:
    def __init__(self, videos_dir: str | Path, on_change: Callable[[], None]):
        self._videos_dir = str(videos_dir)
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="library-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        log.info("library watcher started: %s", self._videos_dir)
        try:
            for _changes in watch(self._videos_dir, stop_event=self._stop):
                try:
                    self._on_change()
                except Exception:
                    log.exception("library watcher callback failed")
        except Exception:
            log.exception("library watcher exited unexpectedly")
        log.info("library watcher stopped")

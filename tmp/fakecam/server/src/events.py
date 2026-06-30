"""Thread-safe SSE event bus.

Publishers may be sync or running on the GStreamer thread; subscribers
run inside the asyncio event loop (FastAPI handlers). All cross-thread
enqueues go through `loop.call_soon_threadsafe`. The bus drops the
oldest event in a subscriber's queue when the queue is full so a slow
client cannot block fast publishers.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional


log = logging.getLogger(__name__)


QUEUE_MAX = 64


class EventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribers: list[asyncio.Queue] = []

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event: dict) -> None:
        if self._loop is None:
            return
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                self._loop.call_soon_threadsafe(_enqueue, q, event)
            except RuntimeError:
                # @claude Loop is shutting down; safe to skip.
                pass


def _enqueue(q: asyncio.Queue, event: dict) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
            q.put_nowait(event)
        except Exception:
            pass

"""
Pipeline lifecycle policy for the app runtime.

Keeps start/restart eligibility, idle reasons, and watchdog-triggered
restart requests separate from the concrete GStreamer operations in
main.py.
"""

from collections.abc import Callable
from typing import Any


class PipelineLifecycle:
    """Small policy object around pipeline start and restart requests."""

    def __init__(self, app_state: Any, is_camera_ready: Callable[[], bool]):
        self._app_state = app_state
        self._is_camera_ready = is_camera_ready
        self._refs: tuple[Any, Any] | None = None

    def set_refs(self, ring: Any, infer_q: Any) -> None:
        self._refs = (ring, infer_q)

    def request_start(
        self,
        starter: Callable[..., None],
        reason: str = "startup",
        restart: bool = False,
    ) -> bool:
        if self._refs is None:
            return False
        ring, infer_q = self._refs
        starter(ring, infer_q, reason=reason, restart=restart)
        return True

    def request_restart(self, starter: Callable[..., None], reason: str) -> bool:
        return self.request_start(starter, reason=reason, restart=True)

    def mark_waiting_for_vlm(self) -> None:
        self._app_state.mark_pipeline_idle("waiting_for_vlm")

    def mark_waiting_for_camera(self) -> None:
        self._app_state.mark_pipeline_idle("waiting_for_camera")

    def ensure_startup_started(self, starter: Callable[..., None]) -> bool:
        if not self._is_camera_ready():
            self.mark_waiting_for_camera()
            return False
        return self.request_start(starter, reason="startup", restart=False)

    def handle_watchdog_timeout(self, starter: Callable[..., None]) -> bool:
        self._app_state.mark_pipeline_stalled("watchdog_timeout")
        return self.request_restart(starter, "watchdog_timeout")

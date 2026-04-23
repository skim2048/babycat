import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from pipeline_lifecycle import PipelineLifecycle  # noqa: E402


class DummyState:
    def __init__(self):
        self.calls = []

    def mark_pipeline_idle(self, reason):
        self.calls.append(("idle", reason))

    def mark_pipeline_stalled(self, reason):
        self.calls.append(("stalled", reason))


def test_request_restart_returns_false_before_refs_are_published():
    state = DummyState()
    lifecycle = PipelineLifecycle(state, lambda: True)

    calls = []

    def fake_starter(*args, **kwargs):
        calls.append((args, kwargs))

    ok = lifecycle.request_restart(fake_starter, "watchdog_timeout")

    assert ok is False
    assert calls == []


def test_ensure_startup_started_marks_waiting_for_camera_when_camera_is_not_ready():
    state = DummyState()
    lifecycle = PipelineLifecycle(state, lambda: False)

    calls = []
    lifecycle.set_refs("ring", "infer_q")

    def fake_starter(*args, **kwargs):
        calls.append((args, kwargs))

    ok = lifecycle.ensure_startup_started(fake_starter)

    assert ok is False
    assert state.calls == [("idle", "waiting_for_camera")]
    assert calls == []


def test_request_restart_reuses_shared_start_path_with_restart_flag():
    state = DummyState()
    lifecycle = PipelineLifecycle(state, lambda: True)
    lifecycle.set_refs("ring", "infer_q")

    calls = []

    def fake_starter(*args, **kwargs):
        calls.append((args, kwargs))

    ok = lifecycle.request_restart(fake_starter, "camera_apply")

    assert ok is True
    assert calls == [
        (("ring", "infer_q"), {"reason": "camera_apply", "restart": True})
    ]


def test_handle_watchdog_timeout_marks_stalled_then_requests_restart():
    state = DummyState()
    lifecycle = PipelineLifecycle(state, lambda: True)
    lifecycle.set_refs("ring", "infer_q")

    calls = []

    def fake_starter(*args, **kwargs):
        calls.append((args, kwargs))

    ok = lifecycle.handle_watchdog_timeout(fake_starter)

    assert ok is True
    assert state.calls == [("stalled", "watchdog_timeout")]
    assert calls == [
        (("ring", "infer_q"), {"reason": "watchdog_timeout", "restart": True})
    ]

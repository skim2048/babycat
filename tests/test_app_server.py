import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import server as server_module  # noqa: E402


class ImmediateThread:
    def __init__(self, target=None, args=(), daemon=None):
        self._target = target
        self._args = args

    def start(self):
        if self._target is not None:
            self._target(*self._args)


def test_camera_restart_uses_registered_callback(monkeypatch):
    calls = []

    monkeypatch.setattr(server_module.threading, "Thread", ImmediateThread)
    server_module.set_restart_pipeline_callback(lambda reason: calls.append(reason) or True)

    handler = server_module.AppHandler.__new__(server_module.AppHandler)
    handler._schedule_camera_restart()

    assert calls == ["camera_apply"]

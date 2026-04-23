import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import state as state_module  # noqa: E402


class DummyRing:
    def __len__(self):
        return 3


def test_snapshot_preserves_public_runtime_fields(monkeypatch):
    app_state = state_module.AppState()
    app_state._ring = DummyRing()
    app_state._ring_size = 30
    app_state._config = {"TARGET_FPS": 1, "N_FRAMES": 4}
    app_state.frame_w = 1920
    app_state.frame_h = 1080
    app_state.infer_label = "person detected"
    app_state.infer_raw = "person standing"
    app_state.infer_ms = 1723.44
    app_state.inference_prompt = "Describe what you see."
    app_state.trigger_keywords = ["person", "fire"]
    app_state.event_triggered = True
    app_state.vlm_state = "ready"
    app_state.vlm_error = ""
    app_state.vlm_models = ["Efficient-Large-Model/VILA1.5-3b"]
    app_state.vlm_current_model = "Efficient-Large-Model/VILA1.5-3b"
    app_state.pipeline_state = "streaming"
    app_state.pipeline_status_reason = ""
    app_state.pipeline_started_at = 100.0
    app_state.pipeline_last_frame_at = 195.0
    app_state.pipeline_restart_count = 2

    monkeypatch.setattr(app_state._hw, "snapshot", lambda: {
        "cpu_percent": 10.0,
        "ram_used_mb": 100,
        "ram_total_mb": 200,
        "gpu_load": 5.0,
        "cpu_temp": 40.0,
        "gpu_temp": 41.0,
    })
    monkeypatch.setattr(state_module.ptz, "get_current", lambda: {"pan": 0.1, "tilt": 0.2})
    monkeypatch.setattr(state_module.ptz, "get_saved", lambda: {"pan": 0.3, "tilt": 0.4})
    monkeypatch.setattr(app_state, "list_clips", lambda: [{"name": "a.mp4"}, {"name": "b.mp4"}])
    monkeypatch.setattr(state_module.time, "time", lambda: 200.0)

    snap = app_state.snapshot()

    assert snap["frame_w"] == 1920
    assert snap["frame_h"] == 1080
    assert snap["infer_label"] == "person detected"
    assert snap["infer_raw"] == "person standing"
    assert snap["infer_ms"] == 1723.4
    assert snap["ring_len"] == 3
    assert snap["ring_size"] == 30
    assert snap["inference_prompt"] == "Describe what you see."
    assert snap["trigger_keywords"] == "person,fire"
    assert snap["event_triggered"] is True
    assert snap["clip_count"] == 2
    assert snap["ptz_pan"] == 0.1
    assert snap["ptz_saved_tilt"] == 0.4
    assert snap["vlm_state"] == "ready"
    assert snap["vlm_models"] == ["Efficient-Large-Model/VILA1.5-3b"]
    assert snap["pipeline_state"] == "streaming"
    assert snap["pipeline_status_reason"] == ""
    assert snap["pipeline_source_protocol"] == "rtsp"
    assert snap["pipeline_source_transport"] == "tcp"
    assert snap["pipeline_active_for_s"] == 100.0
    assert snap["pipeline_last_frame_age_s"] == 5.0
    assert snap["pipeline_restart_count"] == 2
    assert snap["cfg_TARGET_FPS"] == 1
    assert snap["cfg_N_FRAMES"] == 4


def test_runtime_snapshot_locked_formats_trigger_keywords_and_config():
    app_state = state_module.AppState()
    app_state._ring = DummyRing()
    app_state._ring_size = 5
    app_state._config = {"TARGET_FPS": 2}
    app_state.inference_prompt = "Prompt"
    app_state.trigger_keywords = ["a", "b"]
    app_state.event_triggered = False
    app_state.vlm_state = "switching"
    app_state.vlm_error = "none"
    app_state.vlm_models = ["m1", "m2"]
    app_state.vlm_current_model = "m2"

    snap = app_state._owned_runtime_snapshot_locked()

    assert snap["ring_len"] == 3
    assert snap["ring_size"] == 5
    assert snap["inference_prompt"] == "Prompt"
    assert snap["trigger_keywords"] == "a,b"
    assert snap["event_triggered"] is False
    assert snap["vlm_state"] == "switching"
    assert snap["vlm_error"] == "none"
    assert snap["vlm_models"] == ["m1", "m2"]
    assert snap["vlm_current_model"] == "m2"
    assert snap["cfg_TARGET_FPS"] == 2


def test_clip_cache_helper_preserves_dir_and_invalidation(monkeypatch):
    cache = state_module.ClipIndexCache()
    cache.set_dir("/tmp/clips")

    assert cache.get_dir() == "/tmp/clips"

    monkeypatch.setattr(state_module.Path, "exists", lambda self: False)
    assert cache.list() == []

    cache._entries = [{"name": "a.mp4"}]
    cache.invalidate()
    assert cache.list() == []


def test_pipeline_transition_helpers_update_public_stream_state(monkeypatch):
    app_state = state_module.AppState()
    pushes = []

    monkeypatch.setattr(app_state, "_sse_push", lambda: pushes.append("push"))
    monkeypatch.setattr(state_module.time, "time", lambda: 50.0)

    app_state.mark_pipeline_idle("waiting_for_camera")
    assert app_state.pipeline_state == "idle"
    assert app_state.pipeline_status_reason == "waiting_for_camera"

    app_state.mark_pipeline_starting("startup", restart=False, started_at=60.0)
    assert app_state.pipeline_state == "starting"
    assert app_state.pipeline_status_reason == "startup"
    assert app_state.pipeline_started_at == 60.0
    assert app_state.pipeline_restart_count == 0

    app_state.mark_pipeline_starting("watchdog_timeout", restart=True, started_at=70.0)
    assert app_state.pipeline_state == "restarting"
    assert app_state.pipeline_status_reason == "watchdog_timeout"
    assert app_state.pipeline_started_at == 70.0
    assert app_state.pipeline_restart_count == 1

    app_state.mark_pipeline_stalled("watchdog_timeout")
    assert app_state.pipeline_state == "stalled"
    assert app_state.pipeline_status_reason == "watchdog_timeout"

    app_state.mark_pipeline_stopped("shutdown")
    assert app_state.pipeline_state == "stopped"
    assert app_state.pipeline_status_reason == "shutdown"

    assert pushes == ["push", "push", "push", "push", "push"]

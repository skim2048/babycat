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

    snap = app_state._runtime_snapshot_locked()

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

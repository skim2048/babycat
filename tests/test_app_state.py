import os
import sys
from pathlib import Path

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
    app_state.clip_storage_state = "ok"
    app_state.clip_storage_reason = "pruned_old_clips"
    app_state.clip_storage_free_mb = 512
    app_state.vlm_state = "ready"
    app_state.vlm_error = ""
    app_state.vlm_models = ["Efficient-Large-Model/VILA1.5-3b"]
    app_state.vlm_current_model = "Efficient-Large-Model/VILA1.5-3b"
    app_state.pipeline_state = "streaming"
    app_state.pipeline_state_detail = ""
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
    assert snap["clip_storage_state"] == "ok"
    assert snap["clip_storage_reason"] == "pruned_old_clips"
    assert snap["clip_storage_free_mb"] == 512
    assert snap["ptz_pan"] == 0.1
    assert snap["ptz_saved_tilt"] == 0.4
    assert snap["vlm_state"] == "ready"
    assert snap["vlm_models"] == ["Efficient-Large-Model/VILA1.5-3b"]
    assert snap["pipeline_state"] == "streaming"
    assert snap["pipeline_state_detail"] == ""
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
    app_state.clip_storage_state = "skipped"
    app_state.clip_storage_reason = "low_disk_space"
    app_state.clip_storage_free_mb = 42
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
    assert snap["clip_storage_state"] == "skipped"
    assert snap["clip_storage_reason"] == "low_disk_space"
    assert snap["clip_storage_free_mb"] == 42
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


def test_clip_cache_lists_only_completed_clips(tmp_path: Path):
    cache = state_module.ClipIndexCache()
    cache.set_dir(str(tmp_path))

    complete = tmp_path / "2026" / "04" / "complete.mp4"
    complete.parent.mkdir(parents=True)
    complete.write_bytes(b"\x00" * 20480)
    complete.with_suffix(".json").write_text(
        '{"timestamp": 111, "keywords": ["person"], "vlm_text": "standing"}',
        encoding="utf-8",
    )

    pending = tmp_path / "2026" / "04" / "pending.mp4"
    pending.write_bytes(b"\x00" * 20480)

    broken = tmp_path / "2026" / "04" / "broken.mp4"
    broken.write_bytes(b"\x00" * 20480)
    broken.with_suffix(".json").write_text("{", encoding="utf-8")

    clips = cache.list()

    assert [clip["name"] for clip in clips] == ["complete.mp4"]
    assert clips[0]["timestamp"] == 111
    assert clips[0]["keywords"] == ["person"]
    assert clips[0]["vlm_text"] == "standing"


def test_pipeline_transition_helpers_update_public_stream_state(monkeypatch):
    app_state = state_module.AppState()
    pushes = []

    monkeypatch.setattr(app_state, "_sse_push", lambda: pushes.append("push"))
    monkeypatch.setattr(state_module.time, "time", lambda: 50.0)

    app_state.mark_pipeline_idle("waiting_for_camera")
    assert app_state.pipeline_state == "idle"
    assert app_state.pipeline_state_detail == "waiting_for_camera"

    app_state.mark_pipeline_starting("startup", restart=False, started_at=60.0)
    assert app_state.pipeline_state == "starting"
    assert app_state.pipeline_state_detail == "startup"
    assert app_state.pipeline_started_at == 60.0
    assert app_state.pipeline_restart_count == 0

    app_state.mark_pipeline_starting("watchdog_timeout", restart=True, started_at=70.0)
    assert app_state.pipeline_state == "restarting"
    assert app_state.pipeline_state_detail == "watchdog_timeout"
    assert app_state.pipeline_started_at == 70.0
    assert app_state.pipeline_restart_count == 1

    app_state.mark_pipeline_stalled("watchdog_timeout")
    assert app_state.pipeline_state == "stalled"
    assert app_state.pipeline_state_detail == "watchdog_timeout"

    app_state.mark_pipeline_stopped("shutdown")
    assert app_state.pipeline_state == "stopped"
    assert app_state.pipeline_state_detail == "shutdown"

    assert pushes == ["push", "push", "push", "push", "push"]


def test_set_vlm_state_ready_clears_stale_waiting_for_vlm_detail(monkeypatch):
    app_state = state_module.AppState()
    pushes = []

    app_state.pipeline_state = "streaming"
    app_state.pipeline_state_detail = "waiting_for_vlm"
    monkeypatch.setattr(app_state, "_sse_push", lambda: pushes.append("push"))

    app_state.set_vlm_state("ready")

    assert app_state.vlm_state == "ready"
    assert app_state.pipeline_state_detail == ""
    assert pushes == ["push"]


def test_stream_snapshot_hides_waiting_for_vlm_when_vlm_ready(monkeypatch):
    app_state = state_module.AppState()
    app_state.pipeline_state = "streaming"
    app_state.pipeline_state_detail = "waiting_for_vlm"
    app_state.vlm_state = "ready"
    monkeypatch.setattr(state_module.time, "time", lambda: 200.0)

    snap = app_state._stream_snapshot_locked()

    assert snap["pipeline_state"] == "streaming"
    assert snap["pipeline_state_detail"] == ""


def test_set_clip_storage_status_updates_public_snapshot_and_pushes(monkeypatch):
    app_state = state_module.AppState()
    pushes = []

    monkeypatch.setattr(app_state, "_sse_push", lambda: pushes.append("push"))

    app_state.set_clip_storage_status("error", "ffmpeg_failed", 17)

    assert app_state.clip_storage_state == "error"
    assert app_state.clip_storage_reason == "ffmpeg_failed"
    assert app_state.clip_storage_free_mb == 17
    assert pushes == ["push"]

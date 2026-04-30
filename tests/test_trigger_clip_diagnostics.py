import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import trigger_clip_diagnostics as diagnostics  # noqa: E402


def test_summarize_ffmpeg_stderr_keeps_trailing_nonempty_lines():
    stderr = b"\nheader\n\nline1\nline2\nline3\n"
    summary = diagnostics.summarize_ffmpeg_stderr(stderr, max_lines=2)
    assert summary == "line2\nline3"


def test_probe_clip_duration_seconds_parses_ffprobe_output(monkeypatch):
    class DummyResult:
        returncode = 0
        stdout = b"5.042\n"

    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: DummyResult())
    assert diagnostics.probe_clip_duration_seconds(Path("/tmp/sample.mp4")) == 5.042


def test_build_trigger_clip_meta_includes_diagnostics():
    meta = diagnostics.build_trigger_clip_meta(
        event_time=100.25,
        matched_keywords=["person"],
        vlm_text="person walking",
        record_requested_at=100.4,
        ffmpeg_started_at=101.0,
        ffmpeg_elapsed_ms=5200,
        clip_size_bytes=123456,
        clip_duration_s=4.987,
    )
    assert meta["timestamp"] == 100
    assert meta["event_time_ms"] == 100250
    assert meta["start_delay_ms"] == 750
    assert meta["ffmpeg_elapsed_ms"] == 5200
    assert meta["clip_size_bytes"] == 123456
    assert meta["clip_duration_s"] == 4.987
    assert meta["capture_source"] == "mediamtx_rtsp"
    assert meta["video_codec_mode"] == "copy"

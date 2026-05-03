import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import trigger_clip_rollover as rollover  # noqa: E402


def test_segment_path_round_trips_through_parser(tmp_path: Path):
    path = rollover.segment_path_for_time(tmp_path, 1777508120.0)
    started_at = rollover.parse_segment_start(path)
    assert started_at is not None
    assert int(started_at) == 1777508120


def test_select_segments_for_window_filters_overlap(tmp_path: Path):
    for stamp in ("20260430_091518", "20260430_091519", "20260430_091520", "20260430_091521"):
        (tmp_path / f"{stamp}.ts").write_bytes(b"x")

    selected = rollover.select_segments_for_window(
        tmp_path,
        1777508119.5,
        1777508121.1,
        segment_span_s=1.0,
    )

    assert [path.name for path in selected] == [
        "20260430_091519.ts",
        "20260430_091520.ts",
        "20260430_091521.ts",
    ]


def test_write_concat_manifest_uses_ffmpeg_file_lines(tmp_path: Path):
    first = tmp_path / "a.ts"
    second = tmp_path / "b.ts"
    first.write_bytes(b"a")
    second.write_bytes(b"b")

    manifest = rollover.write_concat_manifest([first, second], tmp_path / "segments.txt")
    assert manifest.read_text(encoding="utf-8") == f"file '{first}'\nfile '{second}'\n"


def test_purge_old_segments_removes_only_older_than_threshold(tmp_path: Path):
    old = tmp_path / "20260430_091500.ts"
    keep = tmp_path / "20260430_091520.ts"
    old.write_bytes(b"x")
    keep.write_bytes(b"x")

    removed = rollover.purge_old_segments(tmp_path, retain_since=1777508120.0)

    assert removed == 1
    assert old.exists() is False
    assert keep.exists() is True


def test_latest_segment_age_seconds_uses_latest_segment_timestamp(tmp_path: Path):
    (tmp_path / "20260430_091500.ts").write_bytes(b"x")
    (tmp_path / "20260430_091520.ts").write_bytes(b"x")

    age = rollover.latest_segment_age_seconds(tmp_path, now=1777508125.0)

    assert age == 5.0


def test_segment_recorder_cmd_reencodes_with_forced_keyframes(tmp_path: Path):
    cmd = rollover.segment_recorder_cmd(
        "rtsp://example/live",
        tmp_path,
        segment_time_s=1,
    )

    joined = " ".join(cmd)
    assert "-c:v libx264" in joined
    assert "-force_key_frames expr:gte(t,n_forced*1)" in joined
    assert "-segment_time 1" in joined
    assert "-c copy" not in joined

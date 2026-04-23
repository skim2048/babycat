import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import clip_storage  # noqa: E402


def test_ensure_clip_capacity_keeps_clips_when_free_space_is_sufficient(monkeypatch, tmp_path: Path):
    policy = clip_storage.ClipStoragePolicy(
        min_free_bytes=100,
        target_free_bytes=200,
        prune_max_files=3,
    )
    clip = tmp_path / "2026" / "04" / "20260423_120000_001.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x" * 10)

    monkeypatch.setattr(clip_storage, "free_bytes", lambda path: 250)

    result = clip_storage.ensure_clip_capacity(tmp_path, policy)

    assert result.ok is True
    assert result.reason == "ok"
    assert result.deleted_files == 0
    assert clip.exists()


def test_ensure_clip_capacity_prunes_oldest_clips_until_target_is_met(monkeypatch, tmp_path: Path):
    policy = clip_storage.ClipStoragePolicy(
        min_free_bytes=100,
        target_free_bytes=200,
        prune_max_files=5,
    )
    old_clip = tmp_path / "2026" / "04" / "20260423_120000_001.mp4"
    new_clip = tmp_path / "2026" / "04" / "20260423_120010_001.mp4"
    old_clip.parent.mkdir(parents=True)
    old_clip.write_bytes(b"a" * 10)
    old_clip.with_suffix(".json").write_text("{}", encoding="utf-8")
    new_clip.write_bytes(b"b" * 10)
    new_clip.with_suffix(".json").write_text("{}", encoding="utf-8")
    os.utime(old_clip, (1, 1))
    os.utime(new_clip, (2, 2))

    free_values = iter([50, 220])
    monkeypatch.setattr(clip_storage, "free_bytes", lambda path: next(free_values))

    result = clip_storage.ensure_clip_capacity(tmp_path, policy)

    assert result.ok is True
    assert result.reason == "pruned_old_clips"
    assert result.deleted_files == 1
    assert old_clip.exists() is False
    assert old_clip.with_suffix(".json").exists() is False
    assert new_clip.exists() is True


def test_ensure_clip_capacity_fails_when_pruning_cannot_reach_minimum(monkeypatch, tmp_path: Path):
    policy = clip_storage.ClipStoragePolicy(
        min_free_bytes=100,
        target_free_bytes=200,
        prune_max_files=1,
    )
    clip = tmp_path / "2026" / "04" / "20260423_120000_001.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"x" * 10)

    free_values = iter([50, 80])
    monkeypatch.setattr(clip_storage, "free_bytes", lambda path: next(free_values))

    result = clip_storage.ensure_clip_capacity(tmp_path, policy)

    assert result.ok is False
    assert result.reason == "low_disk_space"
    assert result.deleted_files == 1


def test_cleanup_partial_outputs_removes_existing_files(tmp_path: Path):
    clip = tmp_path / "partial.mp4"
    meta = tmp_path / "partial.json"
    clip.write_bytes(b"data")
    meta.write_text("{}", encoding="utf-8")

    clip_storage.cleanup_partial_outputs(clip, meta)

    assert clip.exists() is False
    assert meta.exists() is False

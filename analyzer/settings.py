"""Analyzer settings persistence (prompt, keywords, labels, presets,
analysis-active; FR-014)."""

import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

STATE_PATH = os.getenv("STATE_PATH", "/data/state/analyzer.json")
PROMPT_DEFAULT = "Describe the scene."  # @claude FR-026 default.

_lock = threading.Lock()


def clean_labels(data) -> dict:
    """Keep only {str: [str, ...]} entries; everything else is dropped. @claude"""
    if not isinstance(data, dict):
        return {}
    labels = {}
    for name, syns in data.items():
        if isinstance(name, str) and name.strip() and isinstance(syns, list):
            words = [s.strip().lower() for s in syns if isinstance(s, str) and s.strip()]
            labels[name.strip()] = words
    return labels


def clean_presets(data) -> list:
    """
    Keep only well-formed presets: {"id": str, "start": "HH:MM",
    "end": "HH:MM", "prompt"?: str, "labels"?: {...}}. The analyzer treats
    id/prompt/labels as opaque client-injected strings; only the time
    range has meaning here.

    @claude
    """
    if not isinstance(data, list):
        return []
    presets = []
    for p in data:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        start = _parse_hhmm(p.get("start"))
        end = _parse_hhmm(p.get("end"))
        if not (isinstance(pid, str) and pid.strip()) or start is None or end is None:
            continue
        preset = {"id": pid.strip(), "start": p["start"], "end": p["end"]}
        if isinstance(p.get("prompt"), str) and p["prompt"].strip():
            preset["prompt"] = p["prompt"].strip()
        if p.get("labels") is not None:
            preset["labels"] = clean_labels(p["labels"])
        presets.append(preset)
    return presets


def validate_labels(data) -> dict | None:
    """Strict form of clean_labels for the HTTP handler: any malformed
    group or synonym rejects the whole payload (no partial apply, same
    rule as /prompt). Returns the normalized dict or None. @claude"""
    if not isinstance(data, dict):
        return None
    cleaned = clean_labels(data)
    if len(cleaned) != len(data):
        return None
    sent = sum(len(v) for v in data.values() if isinstance(v, list))
    kept = sum(len(v) for v in cleaned.values())
    return cleaned if kept == sent else None


def validate_presets(data) -> list | None:
    """Strict form of clean_presets: any malformed preset rejects the
    whole payload. Nested labels are validated strictly too. @claude"""
    if not isinstance(data, list):
        return None
    for p in data:
        if not isinstance(p, dict) or p.get("labels") is not None and validate_labels(p["labels"]) is None:
            return None
    cleaned = clean_presets(data)
    return cleaned if len(cleaned) == len(data) else None


def _parse_hhmm(value) -> int | None:
    """ "HH:MM" -> minutes since midnight, or None when malformed. @claude"""
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def resolve_preset(presets: list, now: float | None = None) -> dict | None:
    """
    Return the first preset whose [start, end) range contains the current
    local time (container TZ). A range with start >= end wraps midnight
    (e.g. 22:00-06:00). Overlaps resolve by list order; no match -> None.

    @claude
    """
    t = time.localtime(now)
    minutes = t.tm_hour * 60 + t.tm_min
    for p in presets:
        start, end = _parse_hhmm(p["start"]), _parse_hhmm(p["end"])
        if start == end:
            continue  # @claude Zero-length range matches nothing.
        if start < end:
            hit = start <= minutes < end
        else:
            hit = minutes >= start or minutes < end
        if hit:
            return p
    return None


def load() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {
        "prompt": data.get("prompt") or PROMPT_DEFAULT,
        "keywords": [k for k in data.get("keywords", []) if isinstance(k, str)],
        "labels": clean_labels(data.get("labels", {})),
        "presets": clean_presets(data.get("presets", [])),
        "analysis_active": bool(data.get("analysis_active", False)),
    }


def save(prompt: str, keywords: list[str], labels: dict, presets: list,
         analysis_active: bool) -> None:
    # @claude Temp file + os.replace: a crash mid-write must not leave a torn
    # @claude file that silently resets the settings on restore (SDD §5.4).
    with _lock:
        try:
            Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
            tmp = f"{STATE_PATH}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"prompt": prompt, "keywords": keywords, "labels": labels,
                     "presets": presets, "analysis_active": analysis_active},
                    f, ensure_ascii=False, indent=2,
                )
            os.replace(tmp, STATE_PATH)
        except OSError as e:
            log.error("settings save failed: %s", e)

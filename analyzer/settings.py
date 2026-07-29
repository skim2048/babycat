"""Analyzer settings persistence (prompt, keywords, analysis-active; FR-014)."""

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

STATE_PATH = os.getenv("STATE_PATH", "/data/state/analyzer.json")
PROMPT_DEFAULT = "Describe the scene."  # @claude FR-026 default.

_lock = threading.Lock()


def load() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    return {
        "prompt": data.get("prompt") or PROMPT_DEFAULT,
        "keywords": [k for k in data.get("keywords", []) if isinstance(k, str)],
        "analysis_active": bool(data.get("analysis_active", False)),
    }


def save(prompt: str, keywords: list[str], analysis_active: bool) -> None:
    # @claude Temp file + os.replace: a crash mid-write must not leave a torn
    # @claude file that silently resets the settings on restore (SDD §5.4).
    with _lock:
        try:
            Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
            tmp = f"{STATE_PATH}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"prompt": prompt, "keywords": keywords, "analysis_active": analysis_active},
                    f, ensure_ascii=False, indent=2,
                )
            os.replace(tmp, STATE_PATH)
        except OSError as e:
            log.error("settings save failed: %s", e)

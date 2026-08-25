"""Recorder operating-state persistence (FR-014, SDD §5.4).

One JSON file carries the buffer-active flag and the event-cooldown
anchor. Writers from different modules (main's buffer endpoints,
finalize's cooldown) merge under one lock, and every write goes through
a temp file + os.replace so a crash mid-write cannot leave a torn file.

@claude
"""

import json
import logging
import os
import threading
from pathlib import Path

from settings import STATE_PATH

log = logging.getLogger(__name__)

_lock = threading.Lock()


def load() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        # @claude A torn file means the restore (FR-014) falls back to defaults;
        # @claude that must be visible, not silent.
        log.warning("state file %s unreadable, using defaults: %s", STATE_PATH, e)
        return {}


def update(**fields) -> None:
    """Merge fields into the state file atomically."""
    with _lock:
        state = load()
        state.update(fields)
        Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{STATE_PATH}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)

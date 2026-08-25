"""
Monitoring stream synthesis (SDD §6.4 (4)).

The router subscribes to the analyzer's SSE for immediate inference and
pipeline updates, polls the recorder's and streamer's /status on a
fixed cadence, and merges the three sources into one flat snapshot per
/state SSE client. A missing source drops its field group but never
stops the stream — observation must survive partial failure.

@claude
"""

import json
import logging
import os
import threading
import time
import urllib.request

log = logging.getLogger(__name__)

ANALYZER_URL = os.environ.get("ANALYZER_URL", "http://analyzer:8080")
RECORDER_URL = os.environ.get("RECORDER_URL", "http://recorder:8080")
STREAMER_URL = os.environ.get("STREAMER_URL", "http://streamer:8080")

POLL_INTERVAL = 2.0
CLIENT_TICK = 0.3

_lock = threading.Lock()
_parts: dict[str, dict | None] = {"analyzer": None, "recorder": None, "streamer": None}
_seq = 0
_started = False


def _bump(source: str, value: dict | None) -> None:
    global _seq
    with _lock:
        _parts[source] = value
        _seq += 1


# @claude Source availability is logged on transition only: a source that is
# @claude down for minutes would otherwise emit one warning per retry.
_available: dict[str, bool | None] = {"analyzer": None, "recorder": None, "streamer": None}


def _note_availability(source: str, ok: bool, error: Exception | None = None) -> None:
    if _available[source] is ok:
        return
    _available[source] = ok
    if ok:
        log.info("monitor source %s available", source)
    else:
        log.warning("monitor source %s unavailable: %s", source, error)


def _analyzer_sse_reader() -> None:
    """Keep one SSE subscription to the analyzer; reconnect on failure."""
    while True:
        try:
            req = urllib.request.Request(f"{ANALYZER_URL}/events", method="GET")
            with urllib.request.urlopen(req, timeout=None) as resp:
                _note_availability("analyzer", True)
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if line.startswith("data: "):
                        try:
                            _bump("analyzer", json.loads(line[len("data: "):]))
                        except json.JSONDecodeError as e:
                            log.warning("analyzer SSE line dropped (invalid JSON): %s", e)
                            continue
        except Exception as e:
            _note_availability("analyzer", False, e)
            _bump("analyzer", None)
            time.sleep(POLL_INTERVAL)


def _poll_json(source: str, url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        _note_availability(source, False, e)
        return None
    _note_availability(source, True)
    return data


def _status_poller() -> None:
    while True:
        _bump("recorder", _poll_json("recorder", f"{RECORDER_URL}/status"))
        _bump("streamer", _poll_json("streamer", f"{STREAMER_URL}/status"))
        time.sleep(POLL_INTERVAL)


def start_collectors() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_analyzer_sse_reader, daemon=True).start()
    threading.Thread(target=_status_poller, daemon=True).start()


def _merged_snapshot() -> tuple[int, dict]:
    with _lock:
        merged: dict = {}
        for source in ("analyzer", "recorder", "streamer"):
            part = _parts[source]
            if part:
                merged.update(part)
        merged["monitor_sources"] = {
            source: _parts[source] is not None
            for source in ("analyzer", "recorder", "streamer")
        }
        return _seq, merged


def sse_generator():
    """Per-client generator: emit a merged snapshot whenever any source changed."""
    last_seq = -1
    while True:
        seq, merged = _merged_snapshot()
        if seq != last_seq:
            last_seq = seq
            yield f"data: {json.dumps(merged, ensure_ascii=False)}\n\n".encode()
        time.sleep(CLIENT_TICK)

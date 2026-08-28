"""Event notification to the recorder (SRS §2.3 (5), SDD §6.3)."""

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)

RECORDER_URL = os.getenv("RECORDER_URL", "http://recorder:8080")


def notify_event(
    matched_keywords: list[str],
    vlm_text: str,
    event_time: float,
    last_frame_time: float | None = None,
    inference_started_at: float | None = None,
    inference_elapsed_ms: int | None = None,
) -> None:
    """
    Fire the notification and move on. Recording completeness is the
    recorder's responsibility; a lost notification is not retried — a
    persisting situation is re-judged by the next inference (SDD §6.3).
    """
    payload = {
        "keywords": matched_keywords,
        "vlm_text": vlm_text,
        "event_time": event_time,
        "last_frame_time": last_frame_time,
        "inference_started_at": inference_started_at,
        "inference_elapsed_ms": inference_elapsed_ms,
    }
    req = urllib.request.Request(
        f"{RECORDER_URL}/notify",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 300:
                log.error("event notify rejected: HTTP %d", resp.status)
    except Exception as e:
        log.error("event notify failed: %s", e)


def notify_inference(
    judged_at: float,
    vlm_text: str,
    labels: list[str],
    preset: str,
    model: str,
    inference_elapsed_ms: int,
) -> None:
    """
    Persist one inference into the recorder's history (layer 1). Fire-and-forget
    like notify_event: a lost row degrades the aggregate slightly and is not
    retried — the history is a sampled record, not a ledger.
    """
    payload = {
        "judged_at": judged_at,
        "vlm_text": vlm_text,
        "labels": labels,
        "preset": preset,
        "model": model,
        "inference_elapsed_ms": inference_elapsed_ms,
    }
    req = urllib.request.Request(
        f"{RECORDER_URL}/inferences",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 300:
                log.error("inference notify rejected: HTTP %d", resp.status)
    except Exception as e:
        log.error("inference notify failed: %s", e)

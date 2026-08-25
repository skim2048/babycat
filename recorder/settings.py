"""
Recorder configuration — the single place environment variables are read.

Injected values are documented in SDD §8.3; values without an environment
variable are fixed here with their rationale.

@claude
"""

import math
import os

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://streamer:8554/live")
DB_PATH = os.getenv("DB_PATH", "/data/db/recorder.db")
CLIP_DIR = os.getenv("CLIP_DIR", "/data/clips")
STATE_PATH = os.getenv("STATE_PATH", "/data/state/recorder.json")
SEGMENT_DIR = os.getenv("TRIGGER_SEGMENT_DIR", "/run/babycat-segments/live")

TRIGGER_COOLDOWN = float(os.getenv("TRIGGER_COOLDOWN", "30"))
TRIGGER_CLIP_DUR = int(os.getenv("TRIGGER_CLIP_DUR", "5"))
TRIGGER_PRE_EVENT_SEC = float(os.getenv("TRIGGER_PRE_EVENT_SEC", "2"))
TRIGGER_POST_EVENT_SEC = float(os.getenv("TRIGGER_POST_EVENT_SEC", str(TRIGGER_CLIP_DUR)))

CLIP_MIN_FREE_MB = int(os.getenv("CLIP_MIN_FREE_MB", "512"))
CLIP_TARGET_FREE_MB = int(os.getenv("CLIP_TARGET_FREE_MB", "1024"))

# @claude Inference history retention (FR-053); rows older than this are deleted
# @claude on insert. Default 90 days: the client's views need the day, a 14-day
# @claude baseline, and a monthly review (mewly analysis-mewly-impl.md §5) —
# @claude about 780k rows at a 10-second cadence.
INFERENCE_RETENTION_DAYS = int(os.getenv("INFERENCE_RETENTION_DAYS", "90"))

ENCODE_BITRATE = int(os.getenv("RECORDER_ENCODE_BITRATE", "4000000"))
ENCODE_FPS = int(os.getenv("RECORDER_ENCODE_FPS", "30"))

# @claude Segment length in seconds. Fixed: the clip window is cut on segment
# @claude boundaries, so this is the cut resolution (SDD §4.4), not a tuning knob.
SEGMENT_TIME = 1

# @claude Retention window derived from the clip window (SDD §5.1, §5.5): the
# @claude pre-event span, the post-event span, and two segments of slack for
# @claude the open-ended last segment and the cut resolution.
SEGMENT_RETENTION = int(math.ceil(TRIGGER_PRE_EVENT_SEC + TRIGGER_POST_EVENT_SEC + 2 * SEGMENT_TIME))

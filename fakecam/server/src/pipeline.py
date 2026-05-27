"""GStreamer pipeline string builder for fakecam.

Phase 1 emits a single-file launch line for `gst-rtsp-server` to consume
via `GstRTSPMediaFactory.set_launch`. Phase 2 will introduce a `concat`
element fed by multiple input chains for seamless transitions.

The encoder side is intentionally normalized: every input is rescaled,
rate-converted, and re-encoded to a fixed H.264 caps profile so that
downstream RTSP clients never see a caps renegotiation when the input
file changes.
"""

from __future__ import annotations

from .schemas import Settings


RESOLUTION_TABLE: dict[str, tuple[int, int]] = {
    "360p": (640, 360),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}


def resolve_dims(resolution: str) -> tuple[int, int]:
    return RESOLUTION_TABLE[resolution]


def build_launch(file_path: str, settings: Settings) -> str:
    """
    Build a parse_launch string that decodes `file_path` and exposes the
    encoded H.264 stream as the `pay0` payloader. When audio is kept, an
    AAC payloader is exposed as `pay1`.
    """
    width, height = resolve_dims(settings.resolution)
    fps = settings.fps
    bitrate_kbps = settings.bitrate_mbps * 1000
    keyframe_interval = fps  # @claude GOP = 1 second per the design.

    video_chain = (
        f"filesrc location={_escape(file_path)} ! qtdemux name=demux "
        "demux.video_0 "
        "! queue ! h264parse ! avdec_h264 "
        "! videoscale ! videorate ! videoconvert "
        f"! video/x-raw,format=I420,width={width},height={height},framerate={fps}/1,pixel-aspect-ratio=1/1 "
        f"! x264enc bitrate={bitrate_kbps} key-int-max={keyframe_interval} "
        "speed-preset=veryfast tune=zerolatency byte-stream=true "
        "! video/x-h264,profile=baseline "
        "! rtph264pay name=pay0 pt=96 config-interval=1"
    )

    if settings.audio == "keep":
        audio_chain = (
            " demux.audio_0 "
            "! queue ! aacparse "
            "! rtpmp4apay name=pay1 pt=97"
        )
        return f"( {video_chain}{audio_chain} )"

    return f"( {video_chain} )"


def _escape(path: str) -> str:
    """Escape characters that conflict with the parse_launch mini-language."""
    return path.replace("\\", "\\\\").replace('"', '\\"')

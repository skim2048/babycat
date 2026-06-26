"""GStreamer pipeline string builder for fakecam.

The launch string always wires a `concat` element between the decoded
input chain(s) and the shared encoder/payloader chain. The encoder
side is intentionally normalized: every input is rescaled, rate-
converted, and re-encoded to a fixed H.264 caps profile so concat
never has to bridge caps differences between sources.

`build_initial_launch` is parsed once by gst-rtsp-server when a client
first connects; it contains the concat skeleton plus a single input
chain feeding `concat.sink_0`. Subsequent inputs are constructed
programmatically in `rtsp_server._build_input_chain` to sidestep the
parse_bin_from_description delayed-link breakage that occurs when the
chain is reparented into the live pipeline.
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


def build_initial_launch(file_path: str, settings: Settings) -> str:
    width, height = resolve_dims(settings.resolution)
    fps = settings.fps
    bitrate_kbps = settings.bitrate_mbps * 1000
    keyframe_interval = fps

    initial_chain = _input_chain_fragment(file_path)
    encode_chain = (
        "concat name=concat "
        "! videoscale ! videorate ! videoconvert "
        f"! video/x-raw,format=I420,width={width},height={height},framerate={fps}/1,pixel-aspect-ratio=1/1 "
        f"! x264enc bitrate={bitrate_kbps} key-int-max={keyframe_interval} "
        "speed-preset=veryfast tune=zerolatency byte-stream=true "
        "! video/x-h264,profile=baseline "
        "! rtph264pay name=pay0 pt=96 config-interval=1"
    )
    # @claude Audio re-encoding paths would need a second concat; for now the
    # @claude "keep audio" flag is ignored under the concat backend until the
    # @claude requirement is exercised in practice.

    return f"( {initial_chain} ! concat.sink_0 {encode_chain} )"


def _input_chain_fragment(file_path: str) -> str:
    safe = _escape(file_path)
    return (
        f'filesrc location="{safe}" '
        "! qtdemux name=demux demux.video_0 "
        "! queue ! h264parse ! avdec_h264"
    )


def _escape(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.png">
    <img src="docs/assets/banner-light.png" width="640" alt="Babycat">
  </picture>
</p>

<div align="center">
  <img src="https://img.shields.io/badge/Python-444444" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-444444" alt="FastAPI">
  <img src="https://img.shields.io/badge/GStreamer-444444" alt="GStreamer">
  <img src="https://img.shields.io/badge/Docker-444444" alt="Docker">
  <img src="https://img.shields.io/badge/NanoLLM-444444" alt="NanoLLM">
  <img src="https://img.shields.io/badge/NVIDIA%20Jetson-444444" alt="NVIDIA Jetson">
</div>

Babycat is a VLM-based video event-detection backend for the NVIDIA Jetson platform. Given keywords, it watches a live video source, detects the moments that match, and saves each matched span as a video clip.

- Keyword-driven event detection over a live RTSP source, powered by a vision-language model (VLM).
- Automatic clip recording of the segment around each detected event, with a searchable event history.
- Runs on the NVIDIA Jetson platform, using its hardware video encoder/decoder and GPU inference.

Babycat is a **backend**: it exposes an HTTP API and does not ship a user interface. A reference client is provided under [`client/`](client/) as a usage example — see [Client](#client) below.

Long-term trend summarization and audio-based detection are out of scope.

## Architecture

Babycat runs as four containers, one per component, orchestrated by Docker Compose. Only two ports are exposed to the outside; everything else stays on the internal Compose network.

| Component | Container | Responsibility |
|---|---|---|
| Request router | `router` | Single external entry point. Owns accounts, tokens, and authentication; relays every request to the owning component; merges the monitoring stream. |
| Video streamer | `streamer` | Manages the video source (profile, connection, ONVIF PTZ) and re-distributes the live stream (HLS / WebRTC) via an embedded MediaMTX. |
| Video analyzer | `analyzer` | Pulls frames from the stream, runs VLM inference, matches keywords, and notifies the recorder on an event. |
| Event recorder | `recorder` | Assembles event clips, keeps the event history, and reports hardware/storage status. |

Externally published ports:

- `8000/tcp` — Request router. The single control entry point (HTTP API), plus HLS and WebRTC-signaling relays.
- `8189/udp` — Video streamer. WebRTC media/ICE. This is the only path that bypasses the router, for low latency.

## Requirements

- An NVIDIA Jetson board with JetPack (tested on JetPack 6.2.1 / L4T R36.x) and the NVIDIA Container Toolkit.
- The hardware video encoder/decoder devices (`/dev/v4l2-nvdec`, `/dev/v4l2-nvenc`).
- A video source that provides an H.264 RTSP stream (an IP camera, or a substitute source replaying recorded video).
- Docker Engine with the Compose plugin.

## Getting Started

Babycat is distributed as source; images are built on the target device.

```bash
# 1. Configure the environment
cp .env.example .env
# Edit .env — at minimum: HOST_IP, JWT_SECRET, DEFAULT_USER, DEFAULT_PASS, VLM_MODELS

# 2. Build and start
docker compose build
docker compose up -d
```

On the first boot the analyzer pre-compiles the candidate VLM models (minutes to tens of minutes each; the results are cached for later boots), and an initial admin account is created — the first login requires a password change.

Configuration is injected through `.env`; every variable is documented in [`.env.example`](.env.example).

## API

The Request router exposes a single HTTP API on port `8000`. It covers authentication, video-source profile and PTZ, the streaming and analysis lifecycle, clips and event history, and a merged monitoring stream (SSE). See the router service ([`router/`](router/)) for the full route map.

## Client

Babycat has no built-in UI. A reference client — a web dashboard — is provided under [`client/web`](client/web) as an example of how to consume the API. It is a reference implementation and is **not part of the product scope**; it can run on the same host or a separate one, and is started independently:

```bash
cd client/web
docker compose up -d
```

## License

Babycat is released under the [GNU General Public License v3.0](LICENSE).

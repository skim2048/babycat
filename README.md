<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.png">
    <img src="docs/assets/banner-light.png" width="640" alt="Babycat">
  </picture>
</p>

<div align="center">
  <img src="https://img.shields.io/badge/v1.0-2b6e4f" alt="Version">
  <img src="https://img.shields.io/badge/Python-444444" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-444444" alt="FastAPI">
  <img src="https://img.shields.io/badge/GStreamer-444444" alt="GStreamer">
  <img src="https://img.shields.io/badge/Docker-444444" alt="Docker">
  <img src="https://img.shields.io/badge/NanoLLM-444444" alt="NanoLLM">
  <img src="https://img.shields.io/badge/NVIDIA%20Jetson-444444" alt="NVIDIA Jetson">
</div>

<p align="center">English · <a href="README.ko.md">한국어</a></p>

Babycat is a VLM-based video event-detection backend for the NVIDIA Jetson platform. Given keywords, it watches a live video source, detects the moments that match, and saves each matched span as a video clip.

- Keyword-driven event detection over a live RTSP source, powered by a vision-language model (VLM).
- Automatic clip recording of the segment around each detected event, with a searchable event history.
- Runs on the NVIDIA Jetson platform, using its hardware video encoder/decoder and GPU inference.

Babycat is a **backend**: it exposes an HTTP API and does not ship a user interface. Reference clients are provided under [`client/`](client/) as usage examples — see [Client](#client) below.

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

- `8000/tcp` — TLS-terminating gateway (Caddy). The single control entry point (HTTPS API); it forwards every request, including the HLS and WebRTC-signaling relays, to the Request router.
- `8189/udp` — Video streamer. WebRTC media/ICE. This is the only path that bypasses the router, for low latency.

## Requirements

Babycat runs on an NVIDIA Jetson device. The prerequisites below build on one another: the board decides which hardware you have, and how JetPack was flashed decides which of the required software is actually present.

**1. An NVIDIA Jetson board.** A minimum-spec board offers the same functionality, but with fewer resources the choice of runnable VLMs narrows and inference latency grows.

| | Recommended | Minimum |
|---|---|---|
| Jetson module | AGX Orin 64 GB | Orin NX 16 GB |
| Storage | NVMe SSD 512 GB | NVMe SSD 256 GB |

Tested on JetPack 6.2.1 (L4T R36.x). JetPack 7.x is not supported — it changes the GPU driver and device-node layout, and the inference stack depends on the JetPack 6 CUDA generation — so flash the board with JetPack 6.x.

**2. The hardware video encoder and decoder.** Babycat requires both NVENC and NVDEC. Development kits include them by SKU, but the device nodes are provided by JetPack's multimedia stack and may be missing after a bare OS flash. Confirm both exist:

```bash
ls /dev/v4l2-nvdec /dev/v4l2-nvenc
```

If either is absent, install the full JetPack component set on the device with `sudo apt install nvidia-jetpack`.

**3. Docker Engine with the Compose plugin.** Follow the official [Docker Engine install guide](https://docs.docker.com/engine/install/ubuntu/) — JetPack is Ubuntu-based, so use the Ubuntu instructions.

**4. The NVIDIA Container Toolkit.** Required to expose the GPU and hardware codecs to the containers. As with the multimedia stack, it may be missing after a bare flash; it ships with `nvidia-jetpack`, or install it on its own per the [NVIDIA Container Toolkit install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

Separately, a video source that provides an H.264 RTSP stream is required — an IP camera, or a substitute source replaying recorded video.

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

The Request router exposes a single HTTPS API on port `8000` (TLS is terminated by the gateway). It covers authentication, video-source profile and PTZ, client data persistence, the streaming and analysis lifecycle, clips and event history, and a merged monitoring stream (SSE). See the router service ([`router/`](router/)) for the full route map.

The gateway issues its TLS certificate at startup: it takes the addresses from `HOST_IP` (plus `TLS_EXTRA_HOSTS` when set) in `.env`, and creates the private CA that signs it if none exists yet. A changed address or an approaching expiry is picked up on the next start, so nothing has to be run by hand.

Each connecting device registers the CA root (`data/caddy/caddy/pki/authorities/local/root.crt`) in its trust store once. To keep that a single registration across several devices, share the CA: copy the first device's `data/caddy/caddy/pki` directory to the same path on each additional device, and that device signs its own certificate with it at startup.

## Client

Babycat has no built-in UI. Two reference clients are provided under [`client/`](client/) as examples of how to consume the API. They are reference implementations and are **not part of the product scope**; each can run on the same host or a separate one, and is started independently. The backend address is entered on each client's login screen.

**Web dashboard** ([`client/web`](client/web)) — a Vue 3 dashboard for desktop browsers. It runs as a container serving the Vite dev server on port `5173`:

```bash
cd client/web
docker compose up -d
# open http://<host>:5173
```

**Android app** ([`client/android`](client/android)) — a Vue 3 + Capacitor mobile app. The Vite dev server on port `5174` gives a browser preview; building an APK requires a machine with the Android SDK:

```bash
cd client/android
npm install
npm run dev    # browser preview at http://<host>:5174
npm run sync   # build the web assets and sync them into android/
# then open android/ in Android Studio, or: cd android && ./gradlew assembleDebug
```

## License

Babycat is released under the [GNU General Public License v3.0](LICENSE).

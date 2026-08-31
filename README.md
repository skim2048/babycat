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

Babycat is a **backend**: it exposes an HTTP API and does not ship a user interface. Reference clients are provided under [`client/`](client/) as usage examples — see [Client](#client) below.

Long-term trend summarization and audio-based detection are out of scope.

## Limitations

- **Detection is best-effort.** Events are judged by a vision-language model matching keywords against generated scene descriptions. Missed events and false alarms are inherent to this approach and no detection rate is guaranteed.
- **Old clips are deleted automatically.** When free space on the clip volume drops below `CLIP_MIN_FREE_MB`, the oldest clips and their event-history rows are removed until `CLIP_TARGET_FREE_MB` is free. Deleted clips cannot be recovered; each deletion is logged.
- **Private CA.** The API is served over HTTPS, but the certificate chains to a private CA, not a public one. Production devices ship with a per-device CA issued by the manufacturer root, which the mewly app bundles, so no client-side setup is needed; a development device without that file creates its own CA at first boot, and every client device must register that CA root once. Babycat is still meant for a trusted network (a LAN or a VPN such as ZeroTier): the gateway is the only encrypted hop, and the private CA does not make the service safe to expose to the internet.

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

Supported on JetPack 6.2.1 (L4T R36.4.x) only. JetPack 6.2.2 (L4T R36.5) is not supported — the hardware decoder path does not open inside the containers (confirmed 2026-08-27) — and neither is JetPack 7.x, which changes the GPU driver and device-node layout while the inference stack depends on the JetPack 6 CUDA generation. Check with `head -1 /etc/nv_tegra_release`; it must read `R36 (release), REVISION: 4.x`.

**2. JetPack components, Docker Engine, and the NVIDIA Container Toolkit.** A bare flash ships without the NVIDIA GStreamer plugins (`nvv4l2decoder`, `nvv4l2h264enc`) and without Docker. Run the setup script once on the board and reboot:

```bash
sudo tools/setup-jetson.sh
sudo reboot
```

It checks the L4T release, installs `nvidia-jetpack` (which brings the codec plugins and the container toolkit), then installs Docker Engine with the Compose plugin, registers the `nvidia` runtime, and adds you to the `docker` group. The order matters — `nvidia-jetpack` removes a previously installed `docker-ce` — so do not install Docker by hand first. Every later `docker compose up` runs a `preflight` container that verifies the L4T release, the codec device nodes, the NvSciIPC socket, the tegra libraries, and the GStreamer elements, and refuses to start the analyzer and recorder if anything is missing; `docker compose logs preflight` shows the verdict and the fix for each failed item.

Separately, a video source that provides an H.264 RTSP stream is required — an IP camera, or a substitute source replaying recorded video.

## Getting Started

Babycat is distributed as source; images are built on the target device.

```bash
tools/up.sh
```

The script asks for `HOST_IP` and the initial account when `.env` does not exist yet (every other knob keeps its [`.env.example`](.env.example) default), creates the data directories owned by your user (the container runtime would otherwise create them owned by root), builds, starts, and prints the preflight verdict and the certificate issuer. Re-running it later is the normal way to restart the stack; with `.env` present it goes straight to `docker compose up -d --build`.

On the first boot the analyzer downloads and pre-compiles the candidate VLM models (minutes to tens of minutes each; the results are cached under `data/models` for later boots), and an initial admin account is created. The first login response carries `must_change_password: true`; the reference clients turn this into a forced password change.

Every operator-tunable variable is documented in [`.env.example`](.env.example); paths and internal addresses are fixed in `docker-compose.yml`.

## API

The Request router exposes a single HTTPS API on port `8000` (TLS is terminated by the gateway). It covers authentication, video-source profile and PTZ (pan/tilt), client data persistence, the streaming and analysis lifecycle, clips, event and inference history with a summary aggregation, and a merged monitoring stream (SSE). The route table is in the SRS ([`docs/srs/4_external_interface_requirements.md`](docs/srs/4_external_interface_requirements.md)) and the request/response conventions in the SDD ([`docs/sdd/6_interface_design.md`](docs/sdd/6_interface_design.md)).

The gateway issues its TLS certificate at startup: it takes the addresses from `HOST_IP` (plus `TLS_EXTRA_HOSTS` when set) in `.env` and signs with the CA found at `data/caddy/caddy/pki/authorities/local/` — the per-device CA placed there at provisioning (the private `babycat-ca` repository), or a self-created CA when none is present. A changed address or an approaching expiry is picked up on the next start, so nothing has to be run by hand.

Production clients trust the manufacturer root only, so nothing is registered per device. A development device with a self-created CA needs its `root.crt` registered in each client's trust store once. The CA hierarchy, provisioning steps, and key custody are documented in [`docs/ops/pki.md`](docs/ops/pki.md).

## Client

Babycat has no built-in UI. Two reference clients are provided under [`client/`](client/) as examples of how to consume the API. They are reference implementations and are **not part of the product scope**; each can run on the same host or a separate one, and is started independently. The backend address is entered on each client's login screen. Both clients talk to the backend over HTTPS and must trust the device's CA root (see Limitations).

**Web dashboard** ([`client/web`](client/web)) — a Vue 3 dashboard for desktop browsers. The bundled container runs the Vite development server on port `5173`; it is a convenience for trying the dashboard on the LAN, not a production deployment:

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

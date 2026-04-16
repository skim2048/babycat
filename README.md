<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/banner-dark-theme.png">
  <source media="(prefers-color-scheme: light)" srcset="./assets/banner-light-theme.png">
  <img src="./assets/banner-light-theme.png" alt="babycat banner">
</picture>

<p align="center">
  <img src="https://img.shields.io/badge/Docker-2496ED.svg?&logo=Docker&logoColor=fff" alt="Docker">
  <img src="https://img.shields.io/badge/FastAPI-009688.svg?&logo=FastAPI&logoColor=fff" alt="FastAPI">
  <img src="https://img.shields.io/badge/GStreamer-E4222A.svg?&logo=GStreamer&logoColor=fff" alt="GStreamer">
  <img src="https://img.shields.io/badge/NVIDIA-76B900.svg?&logo=NVIDIA&logoColor=fff" alt="NVIDIA">
  <img src="https://img.shields.io/badge/Python-3776AB.svg?&logo=Python&logoColor=fff" alt="Python">
  <img src="https://img.shields.io/badge/SQLite-003B57.svg?&logo=SQLite&logoColor=fff" alt="SQLite">
  <img src="https://img.shields.io/badge/Vue.js-4FC08D.svg?&logo=Vue.js&logoColor=fff" alt="Vue.js">
</p>

## Overview

An edge-AI backend that analyzes RTSP camera streams in real time with a Visual Language Model (VLM) and fires notifications when user-defined conditions are met.

- **Edge AI** — detection through notification runs locally; no cloud dependency.
- **Domain-agnostic** — event conditions are expressed in natural language, not hard-coded rules.
- **Live streaming** — dual HLS / WebRTC protocols for instant browser monitoring.
- **PTZ integration** — ONVIF PTZ control (when the camera supports it).

## Architecture

| Container | Ports | Responsibility |
|---|---|---|
| **App** | 8080 | GStreamer pipeline (with watchdog), VLM inference, trigger detection → ffmpeg clip recording, FCM notifications, PTZ control |
| **MediaMTX** | 8554 / 8888 / 8889 / 8890 | RTSP / HLS / WebRTC streaming. Source is configured at runtime by App via the internal API on :9997 |
| **API Server** | 8000 | Authentication and clips / events / device-token REST API (FastAPI + SQLite WAL) |

## Requirements

| Component | Spec |
|---|---|
| Edge-AI board | NVIDIA Jetson Orin NX 16 GB (JetPack 6.2) |
| Camera | RTSP H.264 IP camera (ONVIF PTZ optional) |
| Software | Docker, NVIDIA Container Runtime |

## Getting Started

```bash
# 1) 호스트 GStreamer plugins (JetPack flash-only 환경에 필수)
#    이 패키지가 없으면 컨테이너의 plugins-bad가 호스트 마운트로 가려져
#    h264parse 등이 사라지고 babycat-app이 GStreamer 파이프라인 init에서 죽음.
sudo apt update
sudo apt install -y gstreamer1.0-plugins-bad gstreamer1.0-plugins-good

# 2) 호스트 IP 등록 (WebRTC ICE candidate에 광고됨). zerotier 또는 LAN IP.
cp .env.example .env
$EDITOR .env   # HOST_IP=<젯슨 IP> 채우기

# 3) Main stack
docker compose up -d --build

# 4) Web dashboard (optional)
cd web && docker compose up -d --build
```

On first launch, open `http://<host>:5173` in a browser. You are redirected to the login page.

- **Default credentials**: `admin` / `admin`
- After signing in, use the **Change Password** button in the dashboard header to set a new password.

In the Camera panel, enter the IP, port and credentials. The settings are applied to MediaMTX and the PTZ module automatically and persisted to `config/cam_profile.json` so they are reloaded on restart.

### Authentication

Every endpoint on both `app:8080` and `api:8000` requires a JWT Bearer token. Unauthenticated requests return `401`.

- Login throttle: **10 consecutive failures → 30-minute lockout**
- Token lifetime: 1 hour (configurable via the `JWT_EXPIRY` environment variable)

## Directory Layout

```
babycat/
├── app/                   # App container sources
│   ├── main.py            # Entry point (GStreamer + VLM + trigger clipping + watchdog)
│   ├── camera.py          # Camera config (persistence + MediaMTX source API)
│   ├── server.py          # HTTP server (SSE, MJPEG, PTZ, Camera, Clips)
│   ├── state.py           # Shared state (ring buffer, inference results, clip cache)
│   ├── ptz.py             # ONVIF PTZ control
│   └── hardware.py        # Jetson hardware monitor (tegrastats parser)
├── api/                   # API server sources
│   ├── main.py            # FastAPI endpoints
│   ├── auth.py            # JWT auth + login throttle
│   ├── database.py        # SQLite (WAL) init
│   └── schemas.py         # Pydantic schemas
├── web/                   # Web dashboard (Vue 3 + Vite)
│   ├── docker-compose.yml # Standalone (cd web && docker compose up -d)
│   └── src/
│       ├── views/         # LoginView, DashboardView
│       ├── components/    # LiveStream, ClipsPanel, CameraPanel, PromptPanel, PtzOverlay, …
│       └── composables/   # useAuth, useCamera, useClips, useSSE, usePtz, useTheme, useFetch
├── config/                # Runtime config (cam_profile.json, mediamtx.yml)
├── data/
│   ├── {YYYY}/{MM}/       # Trigger clips (*.mp4 with sidecar *.json metadata)
│   └── db/                # SQLite database (users, events, devices)
├── docker/                # Dockerfiles for the main stack (app, api)
├── tests/                 # bench_vlm, test_api, test_e2e, test_appsink, test_vlm_pipeline
├── docs/                  # API reference + architecture diagram
└── docker-compose.yml     # Main stack (app + mediamtx + api)
```

## Tech Stack

| Area | Choice |
|---|---|
| VLM inference | NanoLLM + VILA1.5-3b (MLC, INT4 quantization) |
| Video pipeline | GStreamer + nvv4l2decoder (GPU hardware decoding) |
| Streaming | MediaMTX (RTSP / HLS / WebRTC) |
| Notifications | FCM HTTP v1 API (OAuth 2.0) |
| API server | FastAPI + SQLite (WAL) |
| Authentication | JWT (HMAC-SHA256, PBKDF2 password hashing) |
| Web dashboard | Vue 3 + Vite + Vue Router |
| PTZ control | ONVIF SOAP (WS-Security) |

## API Overview

### App (:8080)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/events` | SSE (live inference results + hardware state) |
| GET | `/stream` | MJPEG stream (VLM input frames) |
| GET | `/camera` | Get camera config |
| POST | `/camera` | Apply camera config (restarts GStreamer pipeline on change) |
| POST | `/prompt` | Update VLM prompt / trigger keywords |
| POST | `/ptz` | PTZ control (move / stop / save / goto) |
| GET | `/clips` | List clips |
| GET | `/clip/{name}` | Download clip (Range supported) |
| DELETE | `/clips` | Delete selected clips (removes the matching `.json` sidecar too) |

`/stream` and `/events` also accept a `?token=<jwt>` query parameter, for clients like `EventSource` that cannot set the `Authorization` header.

### API Server (:8000)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/login` | No | Login (returns JWT) |
| POST | `/api/change-password` | Yes | Change password |
| GET | `/health` | No | Health check |
| GET | `/clips` | Yes | List clips |
| GET | `/clips/{name}` | Yes | Download clip (Range supported) |
| DELETE | `/clips` | Yes | Delete selected clips |
| DELETE | `/clips/all` | Yes | Delete all clips |
| GET/POST/DELETE | `/events` | Yes | Event history CRUD |
| GET/POST | `/devices` | Yes | FCM device-token management |
| DELETE | `/devices/{device_id}` | Yes | Remove device token |

Full schema reference: [docs/api.md](docs/api.md)

## Environment Variables

### Shared

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | `babycat-default-secret` | JWT signing secret (must match between App and API) |

### App

| Variable | Default | Description |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://babycat-mediamtx:8554/live` | MediaMTX RTSP URL |
| `VLM_MODEL` | `Efficient-Large-Model/VILA1.5-3b` | VLM model ID |
| `TARGET_FPS` | `1.0` | Frame sampling FPS |
| `N_FRAMES` | `4` | Frames per inference |
| `RING_SIZE` | `30` | Ring buffer size (frames) |
| `TRIGGER_COOLDOWN` | `30` | Minimum gap between trigger clips (seconds) |
| `TRIGGER_CLIP_DUR` | `5` | Trigger clip duration (seconds) |
| `CONFIG_PATH` | `/config/cam_profile.json` | Camera profile file path |
| `DATA_DIR` | `/data` | Base dir for trigger clips (`{YYYY}/{MM}/` created underneath) |
| `FCM_CREDENTIALS` | — | Path to FCM service-account JSON |
| `FCM_TOKEN` | — | Target device FCM token |

### API Server

| Variable | Default | Description |
|---|---|---|
| `CAM_DIR` | `/data` | Clip lookup base (shares the same volume as App's `DATA_DIR`) |
| `DB_PATH` | `/data/db/babycat.db` | SQLite database path |
| `JWT_EXPIRY` | `3600` | Token lifetime (seconds) |
| `DEFAULT_USER` | `admin` | Initial admin username |
| `DEFAULT_PASS` | `admin` | Initial admin password |

## Known Limitations

| Item | Details |
|---|---|
| VLM inference latency | With VILA1.5-3b on Jetson Orin NX 16 GB: ~1700 ms for 1 frame, ~4200 ms for 4 frames. CLIP TensorRT is disabled on 16 GB boards (internal threshold is 20 GB) and falls back to Transformers. |
| VLM output format | VILA1.5-3b does not reliably follow strict output templates such as `DETECTED:XX` / `CONFIDENCE:XX`. Free-form generation plus trigger-keyword matching is more robust in practice. |
| Container GPU decoding | `nvv4l2decoder` inside a container requires the `kmod` package. Without `lsmod`, GStreamer falls back to the `cuvidv4l2` path, which fails on Jetson iGPUs. |

## License

Private

![](./assets/banner.png)
<p align="center">
  <img src="https://img.shields.io/badge/Docker-2496ED.svg?&logo=Docker&logoColor=fff" alt="Docker">
  <img src="https://img.shields.io/badge/FastAPI-009688.svg?&logo=FastAPI&logoColor=fff" alt="FastAPI">
  <img src="https://img.shields.io/badge/GStreamer-E4222A.svg?&logo=GStreamer&logoColor=fff" alt="GStreamer">
  <img src="https://img.shields.io/badge/NVIDIA-76B900.svg?&logo=NVIDIA&logoColor=fff" alt="NVIDIA">
  <img src="https://img.shields.io/badge/Python-3776AB.svg?&logo=Python&logoColor=fff" alt="Python">
  <img src="https://img.shields.io/badge/SQLite-003B57.svg?&logo=SQLite&logoColor=fff" alt="SQLite">
  <img src="https://img.shields.io/badge/Vue.js-4FC08D.svg?&logo=Vue.js&logoColor=fff" alt="Vue.js">
</p>

---

An edge AI backend that analyzes RTSP camera streams in real time using a VLM (Visual Language Model) and sends alerts when user-defined conditions are detected.

- **Edge-native** — Runs entirely on NVIDIA Jetson, no cloud inference server required
- **General-purpose detection** — Define detection conditions in natural language via browser UI (VLM prompt + trigger keywords)
- **Zero hardcoding** — Camera credentials are entered from the frontend and persisted to file

---

## Architecture

```
IP Camera (RTSP)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Jetson Orin NX 16GB                            │
│                                                 │
│  ┌─────────────┐    ┌────────────────────────┐  │
│  │  MediaMTX   │◄───│  App (GStreamer+VLM)   │  │
│  │  :8554 RTSP │    │  :8080 API             │  │
│  │  :8888 HLS  │    │                        │  │
│  │  :9997 API  │    │  GStreamer → GPU Decode │  │
│  │             │    │  → Ring Buffer → VLM   │  │
│  │  Segment    │    │  → Event Judge → FCM   │  │
│  │  Recording  │    │                        │  │
│  └─────────────┘    └────────────────────────┘  │
│                              │                  │
│                     ┌────────┴───────┐          │
│                     │  API Server   │          │
│                     │  :8000 REST   │          │
│                     │  SQLite       │          │
│                     └───────────────┘          │
└─────────────────────────────────────────────────┘
```

| Container | Port | Role |
|---|---|---|
| **App** | 8080 | GStreamer pipeline, VLM inference, event detection, FCM alerts, PTZ control |
| **MediaMTX** | 8554/8888/9997 | RTSP/HLS streaming, segment recording, runtime source config via REST API |
| **API Server** | 8000 | Clips/events/device tokens REST API (FastAPI + SQLite) |

---

## Requirements

| Component | Specification |
|---|---|
| Edge AI Board | NVIDIA Jetson Orin NX 16GB (JetPack 6.2) |
| Camera | RTSP H.264 IP camera (ONVIF PTZ optional) |
| Software | Docker, NVIDIA Container Runtime |

---

## Getting Started

```bash
# Start the main stack
docker compose up -d

# Web dashboard (optional)
cd web && docker compose up -d
```

On first launch, camera configuration is required. Enter the camera IP, ports, and credentials in the Camera panel of the web dashboard (`http://<host>:5173`). The settings are automatically applied to MediaMTX and the PTZ module, and persisted to `config/cam_profile.json` for automatic loading on restart.

---

## Directory Structure

```
babycat/
├── app/                   # App container source
│   ├── main.py            # Entry point (GStreamer + VLM + FCM)
│   ├── camera.py          # Camera config management (persistence + MediaMTX API)
│   ├── server.py          # HTTP server (SSE, MJPEG, PTZ, Camera)
│   ├── state.py           # Shared state
│   ├── ptz.py             # ONVIF PTZ control
│   └── hardware.py        # Jetson HW monitor
├── api/                   # API Server source
│   ├── main.py            # FastAPI endpoints
│   ├── database.py        # SQLite (WAL)
│   └── schemas.py         # Pydantic schemas
├── web/                   # Web dashboard (Vue 3 + Vite)
│   ├── docker-compose.yml # Standalone (cd web && docker compose up -d)
│   └── src/               # Vue SFC + Composables
├── config/                # Runtime config (cam_profile.json, mediamtx.yml)
├── data/
│   └── cam/{name}/        # Per-camera clip storage (*.mp4)
├── docker/                # Dockerfiles
├── tests/                 # Tests
├── docs/                  # API reference
├── tmp/                   # Development log (devlog.md)
└── docker-compose.yml     # Main stack
```

---

## Tech Stack

| Area | Technology |
|---|---|
| VLM Inference | NanoLLM + VILA1.5-3b (MLC, INT4 quantization) |
| Video Pipeline | GStreamer + nvv4l2decoder (GPU HW decoding) |
| Streaming | MediaMTX (RTSP/HLS/WebRTC) |
| Notifications | FCM HTTP v1 API (OAuth 2.0) |
| API Server | FastAPI + SQLite (WAL) |
| Web Dashboard | Vue 3 + Vite |
| PTZ Control | ONVIF SOAP (WS-Security) |

---

## API Overview

### App (:8080)

| Method | Path | Description |
|---|---|---|
| GET | `/events` | SSE (real-time inference results + HW status) |
| GET | `/stream` | MJPEG stream (VLM input frames) |
| GET | `/camera` | Get camera configuration |
| POST | `/camera` | Apply camera configuration |
| POST | `/prompt` | Update VLM prompt / trigger keywords |
| POST | `/ptz` | PTZ control |
| GET | `/clips` | List clips |
| GET | `/clip/{name}` | Download clip (Range supported) |
| DELETE | `/clips` | Delete clips |

### API Server (:8000)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET/DELETE | `/clips` | List / delete clips |
| GET/POST/DELETE | `/events` | Event history CRUD |
| GET/POST/DELETE | `/devices` | FCM device token management |

Full schema reference: [docs/api.md](docs/api.md)

---

## Environment Variables

### App

| Variable | Default | Description |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://babycat-mediamtx:8554/live` | MediaMTX RTSP address |
| `VLM_MODEL` | `Efficient-Large-Model/VILA1.5-3b` | VLM model ID |
| `TARGET_FPS` | `1.0` | Frame sampling FPS |
| `N_FRAMES` | `4` | Frames per inference |
| `CONSEC_N` | `3` | Consecutive detection threshold |
| `FCM_CREDENTIALS` | — | FCM service account JSON path |
| `FCM_TOKEN` | — | Target device FCM token |

### API Server

| Variable | Default | Description |
|---|---|---|
| `CAM_DIR` | `/data/cam` | Per-camera clip storage base path |
| `DB_PATH` | `/data/db/babycat.db` | SQLite DB path |

---

## License

Private

## Overview

An edge-AI backend that analyzes RTSP camera streams in real time with a Visual Language Model (VLM) and fires notifications when user-defined conditions are met.

- **Edge AI** — detection through notification runs locally; no cloud dependency.
- **Domain-agnostic** — event conditions are expressed in natural language, not hard-coded rules.
- **Live streaming** — dual HLS / WebRTC protocols for instant browser monitoring.
- **PTZ integration** — ONVIF PTZ control (when the camera supports it).

## Architecture

| Container | Ports | Responsibility |
|---|---|---|
| **App** | 8080 | GStreamer pipeline (with watchdog), VLM inference, trigger detection → ffmpeg clip recording, runtime camera apply, PTZ control, VLM model switching |
| **MediaMTX** | 8554 / 8888 / 8889 / 8890 | RTSP / HLS / WebRTC streaming. Source is configured at runtime by App via the internal API on :9997 |
| **API Server** | 8000 | Authentication, session refresh/logout, camera-profile proxy, and clips / events / device-token REST API (FastAPI + SQLite WAL) |

## Requirements

| Component | Spec |
|---|---|
| Edge-AI board | NVIDIA Jetson Orin NX 16 GB (JetPack 6.2) |
| Camera | RTSP H.264 IP camera (ONVIF PTZ optional) |
| Software | Docker, NVIDIA Container Runtime |

## Getting Started

```bash
sudo apt update
sudo apt install -y nvidia-jetpack

cp .env.example .env
$EDITOR .env   # HOST_IP=<젯슨 IP> 채우기

docker compose up -d --build

cd web
docker compose up -d --build
```

On first launch, open `http://<host>:5173` in a browser. You are redirected to the login page.

- **Default credentials**: `admin` / `admin`
- After signing in, use the **Change Password** button in the dashboard header to set a new password.

The `web` stack expects the main stack to be running first because it joins the external Docker network `babycat`.

In the Camera panel, enter the IP, port and credentials. The settings are applied to MediaMTX and the PTZ module automatically and persisted to `config/cam_profile.json` so they are reloaded on restart.

### Authentication

Protected endpoints on `app:8080` and `api:8000` require a JWT Bearer token. Unauthenticated requests return `401`.

Unauthenticated exceptions:

- `GET app:8080/`
- `GET api:8000/health`
- `POST api:8000/api/login`
- `POST api:8000/api/refresh`
- `POST api:8000/api/logout`

- Login throttle: **10 consecutive failures → 30-minute lockout**
- Access-token lifetime: 10 minutes (configurable via `JWT_EXPIRY`)
- Refresh-token lifetime: 30 days by default (configurable via `REFRESH_EXPIRY`)

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
│   ├── auth.py            # JWT auth + login throttle + refresh-token lifecycle
│   ├── app_proxy.py       # Proxy helpers for camera-profile calls to App
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
| Authentication | JWT access token + refresh token (HMAC-SHA256, PBKDF2 password hashing) |
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
| POST | `/vlm/switch` | Request VLM model switch |
| GET | `/clips` | List clips |
| GET | `/clip/{name}` | Download clip (Range supported) |
| DELETE | `/clips` | Delete selected clips (removes the matching `.json` sidecar too) |

`/stream` and `/events` also accept a `?token=<jwt>` query parameter, for clients like `EventSource` that cannot set the `Authorization` header.

### API Server (:8000)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/login` | No | Login (returns JWT) |
| POST | `/api/refresh` | No | Rotate refresh token and issue a new access token |
| POST | `/api/logout` | No | Revoke refresh token |
| POST | `/api/change-password` | Yes | Change password |
| GET | `/health` | No | Health check |
| GET | `/camera` | Yes | Read persisted camera profile (proxied to App) |
| POST | `/camera` | Yes | Apply camera profile (proxied to App) |
| GET | `/clips` | Yes | List clips |
| GET | `/clips/{name}` | Yes | Download clip (Range supported) |
| DELETE | `/clips` | Yes | Delete selected clips |
| DELETE | `/clips/all` | Yes | Delete all clips |
| GET/POST/DELETE | `/events` | Yes | Event history CRUD |
| GET/POST | `/devices` | Yes | FCM device-token management |
| DELETE | `/devices/{device_id}` | Yes | Remove device token |

Full schema reference: [docs/api.md](docs/api.md)

Internal refactoring boundary guide: [docs/architecture-boundaries.md](docs/architecture-boundaries.md)

## Environment Variables

### Shared

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | `babycat-default-secret` | JWT signing secret (must match between App and API) |
| `HOST_IP` | — | Host IP advertised by MediaMTX as a WebRTC ICE candidate (`.env` / Compose input) |

### App

| Variable | Default | Description |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://babycat-mediamtx:8554/live` | MediaMTX RTSP URL |
| `VLM_MODELS` | `Efficient-Large-Model/VILA1.5-3b` | Comma-separated candidate VLM model IDs; the first entry is the boot default |
| `TARGET_FPS` | `1.0` | Frame sampling FPS |
| `N_FRAMES` | `4` | Frames per inference |
| `RING_SIZE` | `30` | Ring buffer size (frames) |
| `TRIGGER_COOLDOWN` | `30` | Minimum gap between trigger clips (seconds) |
| `TRIGGER_CLIP_DUR` | `5` | Trigger clip duration (seconds) |
| `CLIP_MIN_FREE_MB` | `256` | Minimum free disk required before recording a trigger clip |
| `CLIP_TARGET_FREE_MB` | `512` | Prune target when freeing clip-storage space |
| `CLIP_PRUNE_MAX_FILES` | `20` | Maximum number of old clips pruned in one cleanup pass |
| `CONFIG_PATH` | `/config/cam_profile.json` | Camera profile file path |
| `DATA_DIR` | `/data` | Base dir for trigger clips (`{YYYY}/{MM}/` created underneath) |
| `FCM_CREDENTIALS` | — | Path to FCM service-account JSON |
| `FCM_TOKEN` | — | Target device FCM token |

### API Server

| Variable | Default | Description |
|---|---|---|
| `CAM_DIR` | `/data` | Clip lookup base (shares the same volume as App's `DATA_DIR`) |
| `DB_PATH` | `/data/db/babycat.db` | SQLite database path |
| `JWT_EXPIRY` | `600` | Token lifetime (seconds) |
| `REFRESH_EXPIRY` | `2592000` | Refresh-token lifetime (seconds) |
| `DEFAULT_USER` | `admin` | Initial admin username |
| `DEFAULT_PASS` | `admin` | Initial admin password |
| `BABYCAT_APP_URL` | `http://babycat-app:8080` | Internal App base URL used by the camera proxy |
| `CORS_EXTRA_ORIGINS` | — | Additional allowed origins for the API server |

## Known Limitations

| Item | Details |
|---|---|
| VLM inference latency | With VILA1.5-3b on Jetson Orin NX 16 GB: ~1700 ms for 1 frame, ~4200 ms for 4 frames. CLIP TensorRT is disabled on 16 GB boards (internal threshold is 20 GB) and falls back to Transformers. |
| VLM output format | VILA1.5-3b does not reliably follow strict output templates such as `DETECTED:XX` / `CONFIDENCE:XX`. Free-form generation plus trigger-keyword matching is more robust in practice. |
| Container GPU decoding | `nvv4l2decoder` inside a container requires the `kmod` package. Without `lsmod`, GStreamer falls back to the `cuvidv4l2` path, which fails on Jetson iGPUs. |

## License

Private

> 🌐 **Language:** **English** · [한국어](README.ko.md)

# Babycat

An edge AI system that analyzes RTSP camera streams in real time. A VLM (Vision Language Model) watches the live feed, and when it detects a user-defined condition, the system records an event clip and sends a notification.

- **Edge-only** — every step from detection to notification runs locally on the device. No cloud dependency.
- **Free-form conditions** — event conditions are expressed in natural language. No rules hard-coded into the codebase.
- **Dual streaming** — HLS and WebRTC are both available for real-time monitoring in the browser.
- **PTZ integration** — supports ONVIF PTZ cameras.

## Architecture

| Container | Port | Role |
|---|---|---|
| **App** | 8080 | GStreamer pipeline (with watchdog), VLM inference, trigger detection, event clip recording, PTZ control, camera profile application, VLM model switching |
| **MediaMTX** | 8554 / 8888 / 8889 / 8890 | RTSP / HLS / WebRTC streaming server. Source is configured at runtime by App via the internal API (`:9997`) |
| **API Server** | 8000 | Authentication, session refresh/logout, camera profile proxy, clip/event/device-token REST API (FastAPI + SQLite WAL) |

The web dashboard (`web/`) runs as a separate Compose stack.

## Requirements

| Item | Spec |
|---|---|
| Edge AI board | NVIDIA Jetson Orin NX 16 GB (JetPack 6.2, L4T R36.5.x) |
| Camera | RTSP H.264 IP camera (ONVIF PTZ optional) |
| Software | Docker, NVIDIA Container Runtime |

## Getting Started

```bash
# 1. Package update (Jetson)
sudo apt update && sudo apt install -y nvidia-jetpack

# 2. Configure environment variables
cp .env.example .env
$EDITOR .env   # set HOST_IP to the Jetson's IP

# 3. Launch the main stack (app + mediamtx + api)
docker compose up -d --build

# 4. Launch the web dashboard (separate stack, runs independently)
cd web
docker compose up -d --build
```

Open `http://<Jetson IP>:5173` in a browser. You'll land on the login screen.

- **Default account**: `admin` / `admin`
- After logging in, change the password immediately using the **Change Password** button at the top of the dashboard.

The `web` stack runs independently of the main stack and does not require a shared Docker network. It can run on a separate host; the backend address the browser should connect to is entered on the login screen (once a connection succeeds it is stored in the browser and auto-filled on subsequent visits).

When you enter IP, port, and credentials in the Camera panel, they are applied to the MediaMTX source and the PTZ module immediately and persisted to `config/cam_profile.json`.

### Authentication

Protected endpoints on `app:8080` and `api:8000` require a JWT Bearer token. Requests without a token return `401`.

Endpoints exempted from authentication:

- `GET app:8080/`
- `GET api:8000/health`
- `POST api:8000/api/login`
- `POST api:8000/api/refresh`
- `POST api:8000/api/logout`

- 10 consecutive failed logins → 30-minute lockout
- Access token lifetime: 10 minutes (adjust via `JWT_EXPIRY`)
- Refresh token lifetime: 30 days (adjust via `REFRESH_EXPIRY`)

## Directory Layout

```
babycat/
├── app/                        # App container source
│   ├── main.py                 # Entry point (GStreamer + VLM + trigger clip + watchdog loop)
│   ├── camera.py               # Camera profile persistence + MediaMTX source API
│   ├── server.py               # HTTP server (SSE, MJPEG, PTZ, camera, clips)
│   ├── state.py                # Shared state (ring buffer, inference results, clip cache)
│   ├── hardware.py             # Jetson hardware monitor (CPU / GPU / RAM)
│   ├── pipeline_lifecycle.py   # Pipeline creation, teardown, restart
│   ├── clip_storage.py         # Free-space management + old-clip pruning
│   ├── trigger_clip_rollover.py # Segment-rollover-based clip recording
│   ├── trigger_clip_diagnostics.py # Clip metadata + diagnostic info
│   ├── ptz.py                  # ONVIF PTZ control
│   ├── holder.py               # VLM model singleton holder
│   ├── vlm_worker.py           # VLM inference subprocess (reclaims CUDA/TVM/TensorRT memory on model switch)
│   └── server_support.py       # Server helper utilities (JWT verification, clip path resolution, Range parsing)
├── api/                        # API server source
│   ├── main.py                 # FastAPI endpoints
│   ├── auth.py                 # JWT auth + login throttling + refresh-token lifecycle
│   ├── app_proxy.py            # App camera-profile proxy
│   ├── clip_support.py         # Clip path resolution + Range header parsing helpers
│   ├── database.py             # SQLite (WAL) initialization
│   └── schemas.py              # Pydantic schemas
├── web/                        # Web dashboard (Vue 3 + Vite)
│   ├── docker-compose.yml      # Standalone Compose stack
│   └── src/
│       ├── views/              # LoginView, DashboardView
│       ├── components/         # LiveStream, ClipsPanel, CameraPanel, PromptPanel, PtzOverlay, SystemOverlay, LiveStreamSystemPanel …
│       ├── composables/        # useAuth, useCamera, useClips, useSSE, usePtz, useTheme, useFetch, useLocale …
│       └── i18n/               # Korean / English locales
├── config/                     # Runtime configuration (cam_profile.json, mediamtx.yml)
├── data/
│   ├── {YYYY}/{MM}/            # Trigger clips (*.mp4 + *.json sidecar)
│   ├── db/                     # SQLite database (users, events, devices)
│   └── models/                 # Model cache (MLC-compiled `.so`, HuggingFace snapshots, clip_trt TensorRT engine)
├── docker/                     # Main-stack Dockerfiles (app, api)
├── tests/                      # Test suite (API, pipeline, hardware, VLM benchmarks)
├── docs/                       # API reference + architecture boundary docs
└── docker-compose.yml          # Main stack (app + mediamtx + api)
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
| GET | `/events` | SSE (live inference results + hardware status) |
| GET | `/stream` | MJPEG stream (VLM input frames) |
| GET | `/camera` | Get camera profile |
| POST | `/camera` | Apply camera profile (restarts the GStreamer pipeline on change) |
| POST | `/prompt` | Update VLM prompt / trigger keywords |
| POST | `/ptz` | PTZ control (move / stop / save / goto) |
| POST | `/vlm/switch` | Request a VLM model switch |
| GET | `/clips` | List clips |
| GET | `/clip/{name}` | Download clip (Range supported) |
| DELETE | `/clips` | Delete selected clips (also removes the `.json` sidecar) |

`/stream` and `/events` also accept a `?token=<jwt>` query parameter for clients that cannot set the `Authorization` header (e.g. `EventSource`).

### API Server (:8000)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/login` | none | Log in (returns JWT) |
| POST | `/api/refresh` | none | Rotate refresh token + issue a new access token |
| POST | `/api/logout` | none | Revoke refresh token |
| POST | `/api/change-password` | required | Change password |
| GET | `/health` | none | Health check |
| GET | `/camera` | required | Get camera profile (App proxy) |
| POST | `/camera` | required | Apply camera profile (App proxy) |
| GET | `/clips` | required | List clips |
| GET | `/clips/{name}` | required | Download clip (Range supported) |
| DELETE | `/clips` | required | Delete selected clips |
| DELETE | `/clips/all` | required | Delete all clips |
| GET/POST/DELETE | `/events` | required | Event history CRUD |
| GET/POST | `/devices` | required | Manage FCM device tokens |
| DELETE | `/devices/{device_id}` | required | Delete device token |

Full schema reference: [docs/api.md](docs/api.md)

Architecture boundary guide: [docs/architecture-boundaries.md](docs/architecture-boundaries.md)

## Environment Variables

### Common

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET` | `babycat-default-secret` | JWT signing key (must match between App and API containers) |
| `HOST_IP` | — | Host IP that MediaMTX advertises as a WebRTC ICE candidate. Comma-separated for multiple IPs |

### App

| Variable | Default | Description |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://mtx:8554/live` | MediaMTX RTSP URL (Compose service name `mtx`) |
| `VLM_MODELS` | `Efficient-Large-Model/VILA1.5-3b` | Comma-separated VLM model IDs. The first entry is the boot default |
| `TARGET_FPS` | `1.0` | Frame sampling FPS |
| `N_FRAMES` | `4` | Frames per inference call |
| `RING_SIZE` | `30` | Ring buffer size (frames) |
| `TRIGGER_COOLDOWN` | `30` | Minimum interval between trigger clips (seconds) |
| `TRIGGER_CLIP_DUR` | `5` | Trigger clip duration (seconds) |
| `CLIP_MIN_FREE_MB` | `256` | Minimum free disk required before recording a clip (MB) |
| `CLIP_TARGET_FREE_MB` | `512` | Free-space target after cleanup (MB) |
| `CLIP_PRUNE_MAX_FILES` | `20` | Maximum clips deleted per cleanup pass |
| `CONFIG_PATH` | `/config/cam_profile.json` | Camera profile file path |
| `DATA_DIR` | `/data` | Base directory for trigger clips (created under `{YYYY}/{MM}/`) |
| `FCM_CREDENTIALS` | — | Path to the FCM service-account JSON file |
| `FCM_TOKEN` | — | Target device FCM token |
| `TRIGGER_ROLLOVER_ENABLED` | `0` | Set to `1` to enable segment-rollover-based clip recording |
| `TRIGGER_SEGMENT_DIR` | `/run/babycat-segments/live` | Temporary directory for rollover segments (tmpfs recommended) |

### API Server

| Variable | Default | Description |
|---|---|---|
| `CAM_DIR` | `/data` | Base directory for clip lookups (same volume as App's `DATA_DIR`) |
| `DB_PATH` | `/data/db/babycat.db` | SQLite database path |
| `JWT_EXPIRY` | `600` | Access token lifetime (seconds) |
| `REFRESH_EXPIRY` | `2592000` | Refresh token lifetime (seconds) |
| `DEFAULT_USER` | `admin` | Admin account seeded on first boot |
| `DEFAULT_PASS` | `admin` | Admin password seeded on first boot |
| `BABYCAT_APP_URL` | `http://app:8080` | Internal App URL used by the camera proxy (Compose service name `app`) |
| `CORS_EXTRA_ORIGINS` | — | Additional CORS origins to allow on the API server |

## Known Limitations

| Item | Detail |
|---|---|
| VLM inference latency | On Jetson Orin NX 16 GB: ~1700 ms for 1 frame, ~4200 ms for 4 frames. On a 16 GB board the CLIP TensorRT internal threshold (20 GB) is not met, so the Transformers fallback is used |
| VLM output format | VILA1.5-3b does not reliably follow strict output formats such as `DETECTED:XX`. Free-form generation followed by trigger-keyword matching is more stable in practice |
| In-container GPU decoding | Using `nvv4l2decoder` inside a container requires the `kmod` package. Without `lsmod`, GStreamer falls back to `cuvidv4l2`, which fails on the Jetson iGPU |

## License
GNU General Public License v3.0 (GPL-3.0)

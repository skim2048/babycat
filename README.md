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

## 소개

RTSP 카메라 스트림을 VLM(Visual Language Model)으로 실시간 분석하여, 사용자 정의 조건 감지 시 알림을 전송하는 엣지 AI 백엔드.

- **엣지 AI** — 클라우드 없이 로컬에서 감지부터 알림까지 처리
- **범용 설계** — 도메인 제한 없이 이벤트 조건을 자연어로 정의
- **실시간 스트리밍** — HLS/WebRTC 듀얼 프로토콜로 브라우저에서 즉시 모니터링
- **PTZ 연동** — ONVIF PTZ 제어 (카메라 지원 시)

## 아키텍처

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/architecture-dark-theme.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/architecture-light-theme.svg">
  <img src="./assets/architecture-light-theme.svg" alt="architecture">
</picture>

&nbsp;
| 컨테이너 | 포트 | 역할 |
|---|---|---|
| **App** | 8080 | GStreamer 파이프라인, VLM 추론, 이벤트 감지, FCM 알림, PTZ 제어 |
| **MediaMTX** | 8554/8888/8889/8890 | RTSP/HLS/WebRTC 스트리밍, 세그먼트 녹화, REST API로 소스 동적 설정 (내부 전용) |
| **API Server** | 8000 | 인증, 클립/이벤트/기기토큰 REST API (FastAPI + SQLite) |

---

## 요구사항

| 구성 요소 | 사양 |
|---|---|
| 엣지 AI 보드 | NVIDIA Jetson Orin NX 16GB (JetPack 6.2) |
| 카메라 | RTSP H.264 IP 카메라 (ONVIF PTZ 선택) |
| 소프트웨어 | Docker, NVIDIA Container Runtime |

---

## 시작하기

```bash
# 메인 스택 실행
docker compose up -d

# 웹 대시보드 (선택)
cd web && docker compose up -d
```

최초 실행 시 `http://<host>:5173`에서 웹 대시보드에 접속합니다. 로그인 페이지로 리다이렉트됩니다.

- **기본 자격증명**: `admin` / `admin`
- 로그인 후 대시보드 헤더의 **비밀번호 변경** 버튼으로 비밀번호를 변경하세요.

카메라 패널에서 IP, 포트, 자격증명을 입력합니다. 설정은 MediaMTX와 PTZ 모듈에 자동 적용되며, `config/cam_profile.json`에 영속화되어 재시작 시 자동 로드됩니다.

### 인증

모든 API 엔드포인트(`app:8080`, `api:8000`)는 JWT Bearer 토큰이 필요합니다. 미인증 요청은 `401`을 반환합니다.

- 로그인 시도 제한: **10회 연속 실패 → 30분 잠금**
- 토큰 만료: 1시간 (환경변수 `JWT_EXPIRY`로 조정 가능)

---

## 디렉토리 구조

```
babycat/
├── app/                   # App 컨테이너 소스
│   ├── main.py            # 엔트리포인트 (GStreamer + VLM + FCM)
│   ├── camera.py          # 카메라 설정 관리 (영속화 + MediaMTX API)
│   ├── server.py          # HTTP 서버 (SSE, MJPEG, PTZ, Camera)
│   ├── state.py           # 공유 상태
│   ├── ptz.py             # ONVIF PTZ 제어
│   └── hardware.py        # Jetson 하드웨어 모니터
├── api/                   # API 서버 소스
│   ├── main.py            # FastAPI 엔드포인트
│   ├── auth.py            # JWT 인증 + 로그인 시도 제한
│   ├── database.py        # SQLite (WAL)
│   └── schemas.py         # Pydantic 스키마
├── web/                   # 웹 대시보드 (Vue 3 + Vite)
│   ├── docker-compose.yml # 독립 실행 (cd web && docker compose up -d)
│   └── src/               # Vue SFC + Composables
├── config/                # 런타임 설정 (cam_profile.json, mediamtx.yml)
├── data/
│   ├── cam/{name}/        # 카메라별 클립 저장소 (*.mp4)
│   └── db/                # SQLite 데이터베이스 (users, events, devices)
├── docker/                # Dockerfiles
├── tests/                 # 테스트
├── docs/                  # API 레퍼런스
└── docker-compose.yml     # 메인 스택
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| VLM 추론 | NanoLLM + VILA1.5-3b (MLC, INT4 양자화) |
| 영상 파이프라인 | GStreamer + nvv4l2decoder (GPU 하드웨어 디코딩) |
| 스트리밍 | MediaMTX (RTSP/HLS/WebRTC) |
| 알림 | FCM HTTP v1 API (OAuth 2.0) |
| API 서버 | FastAPI + SQLite (WAL) |
| 인증 | JWT (HMAC-SHA256, PBKDF2 비밀번호 해싱) |
| 웹 대시보드 | Vue 3 + Vite + Vue Router |
| PTZ 제어 | ONVIF SOAP (WS-Security) |

---

## API 개요

### App (:8080)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 상태 확인 |
| GET | `/events` | SSE (실시간 추론 결과 + 하드웨어 상태) |
| GET | `/stream` | MJPEG 스트림 (VLM 입력 프레임) |
| GET | `/camera` | 카메라 설정 조회 |
| POST | `/camera` | 카메라 설정 적용 |
| POST | `/prompt` | VLM 프롬프트 / 트리거 키워드 변경 |
| POST | `/ptz` | PTZ 제어 |
| GET | `/clips` | 클립 목록 |
| GET | `/clip/{name}` | 클립 다운로드 (Range 지원) |
| DELETE | `/clips` | 클립 삭제 |

### API Server (:8000)

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/login` | 불필요 | 로그인 (JWT 반환) |
| POST | `/api/change-password` | 필요 | 비밀번호 변경 |
| GET | `/health` | 불필요 | 상태 확인 |
| GET | `/cameras` | 필요 | 카메라 목록 |
| GET | `/clips` | 필요 | 클립 목록 |
| GET | `/clips/{name}` | 필요 | 클립 다운로드 (Range 지원) |
| DELETE | `/clips` | 필요 | 선택 클립 삭제 |
| DELETE | `/clips/all` | 필요 | 전체 클립 삭제 |
| GET/POST/DELETE | `/events` | 필요 | 이벤트 이력 CRUD |
| GET/POST | `/devices` | 필요 | FCM 기기 토큰 관리 |
| DELETE | `/devices/{device_id}` | 필요 | 기기 토큰 삭제 |

전체 스키마 레퍼런스: [docs/api.md](docs/api.md)

---

## 환경변수

### 공통

| 변수 | 기본값 | 설명 |
|---|---|---|
| `JWT_SECRET` | `babycat-default-secret` | JWT 서명 시크릿 (App과 API 서버 간 일치 필수) |

### App

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://babycat-mediamtx:8554/live` | MediaMTX RTSP 주소 |
| `VLM_MODEL` | `Efficient-Large-Model/VILA1.5-3b` | VLM 모델 ID |
| `TARGET_FPS` | `1.0` | 프레임 샘플링 FPS |
| `N_FRAMES` | `4` | 추론 당 프레임 수 |
| `RING_SIZE` | `30` | Ring Buffer 크기 (프레임 수) |
| `TRIGGER_COOLDOWN` | `30` | 이벤트 클립 녹화 쿨다운 (초) |
| `TRIGGER_CLIP_DUR` | `5` | 이벤트 클립 녹화 길이 (초) |
| `CONFIG_PATH` | `/config/cam_profile.json` | 카메라 프로필 설정 파일 경로 |
| `CAM_BASE_DIR` | `/data/cam` | 카메라별 클립 저장 경로 |
| `FCM_CREDENTIALS` | — | FCM 서비스 계정 JSON 경로 |
| `FCM_TOKEN` | — | 대상 기기 FCM 토큰 |

### API Server

| 변수 | 기본값 | 설명 |
|---|---|---|
| `CAM_DIR` | `/data/cam` | 카메라별 클립 저장 경로 |
| `DB_PATH` | `/data/db/babycat.db` | SQLite DB 경로 |
| `JWT_EXPIRY` | `3600` | 토큰 만료 시간 (초) |
| `DEFAULT_USER` | `admin` | 초기 관리자 사용자명 |
| `DEFAULT_PASS` | `admin` | 초기 관리자 비밀번호 |

---

## 알려진 제약사항

| 항목 | 내용 |
|---|---|
| VLM 추론 속도 | VILA1.5-3b 기준 1프레임 ~1700ms, 4프레임 ~4200ms (Jetson Orin NX 16GB). CLIP TensorRT가 16GB 환경에서 비활성화되어 Transformers로 폴백됨 (내부 임계값 20GB) |
| VLM 출력 포맷 | VILA1.5-3b는 엄격한 출력 포맷 지시(`DETECTED:XX`, `CONFIDENCE:XX`)를 잘 따르지 못함. 자유 서술 + 트리거 키워드 매칭 방식이 더 안정적 |
| 컨테이너 GPU 디코딩 | nvv4l2decoder를 컨테이너에서 사용하려면 `kmod` 패키지 필수. `lsmod`가 없으면 cuvidv4l2 경로로 폴백되어 Jetson iGPU에서 실패 |

---

## 라이선스

Private

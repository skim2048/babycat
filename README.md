# Babycat

RTSP 카메라 스트림을 실시간으로 분석하는 엣지 AI 시스템입니다. VLM(Vision Language Model)이 라이브 영상을 보고 사용자 정의 조건을 감지하면, 이벤트 클립을 저장하고 알림을 전송합니다.

- **엣지 전용** — 감지부터 알림까지 모든 처리가 장치 로컬에서 실행됩니다. 클라우드 의존 없음.
- **자유 형식 조건** — 이벤트 조건을 자연어로 표현합니다. 규칙을 코드에 하드코딩하지 않습니다.
- **이중 스트리밍** — HLS / WebRTC 두 프로토콜로 브라우저 실시간 모니터링을 지원합니다.
- **PTZ 연동** — ONVIF PTZ 카메라를 지원합니다.

## 아키텍처

| 컨테이너 | 포트 | 역할 |
|---|---|---|
| **App** | 8080 | GStreamer 파이프라인(감시 포함), VLM 추론, 트리거 감지, 이벤트 클립 녹화, PTZ 제어, 카메라 설정 적용, VLM 모델 전환 |
| **MediaMTX** | 8554 / 8888 / 8889 / 8890 | RTSP / HLS / WebRTC 스트리밍 서버. 소스는 App이 내부 API(:9997)로 런타임 설정 |
| **API Server** | 8000 | 인증, 세션 갱신/로그아웃, 카메라 프로파일 프록시, 클립·이벤트·디바이스 토큰 REST API (FastAPI + SQLite WAL) |

웹 대시보드(`web/`)는 별도 Compose 스택으로 실행됩니다.

## 요구 사항

| 항목 | 사양 |
|---|---|
| 엣지 AI 보드 | NVIDIA Jetson Orin NX 16 GB (JetPack 6.2, L4T R36.5.x) |
| 카메라 | RTSP H.264 IP 카메라 (ONVIF PTZ 선택) |
| 소프트웨어 | Docker, NVIDIA Container Runtime |

## 시작하기

```bash
# 1. 패키지 업데이트 (Jetson)
sudo apt update && sudo apt install -y nvidia-jetpack

# 2. 환경 변수 설정
cp .env.example .env
$EDITOR .env   # HOST_IP 에 젯슨 IP 입력

# 3. 메인 스택 실행 (app + mediamtx + api)
docker compose up -d --build

# 4. 웹 대시보드 실행 (별도 스택, 독립 실행 가능)
cd web
docker compose up -d --build
```

브라우저에서 `http://<젯슨 IP>:5173` 을 엽니다. 로그인 화면으로 이동합니다.

- **기본 계정**: `admin` / `admin`
- 로그인 후 대시보드 상단 **비밀번호 변경** 버튼으로 즉시 변경하세요.

`web` 스택은 메인 스택과 독립적으로 동작하며 공유 Docker 네트워크가 필요 없습니다. 별도 호스트에서 실행할 수 있고, 브라우저가 접속할 백엔드 위치는 로그인 화면에서 입력합니다(연결 성공 시 브라우저에 저장되어 다음 접속부터 자동 입력).

Camera 패널에서 IP, 포트, 인증 정보를 입력하면 MediaMTX 소스와 PTZ 모듈에 즉시 적용되고 `config/cam_profile.json`에 저장됩니다.

### 인증

`app:8080`과 `api:8000`의 보호 엔드포인트는 JWT Bearer 토큰이 필요합니다. 토큰이 없으면 `401`을 반환합니다.

인증 예외 엔드포인트:

- `GET app:8080/`
- `GET api:8000/health`
- `POST api:8000/api/login`
- `POST api:8000/api/refresh`
- `POST api:8000/api/logout`

- 로그인 실패 10회 연속 → 30분 잠금
- 액세스 토큰 유효 시간: 10분 (`JWT_EXPIRY`로 조정)
- 리프레시 토큰 유효 시간: 30일 (`REFRESH_EXPIRY`로 조정)

## 디렉터리 구조

```
babycat/
├── app/                        # App 컨테이너 소스
│   ├── main.py                 # 진입점 (GStreamer + VLM + 트리거 클립 + 감시 루프)
│   ├── camera.py               # 카메라 설정 영속화 + MediaMTX 소스 API
│   ├── server.py               # HTTP 서버 (SSE, MJPEG, PTZ, 카메라, 클립)
│   ├── state.py                # 공유 상태 (링 버퍼, 추론 결과, 클립 캐시)
│   ├── hardware.py             # Jetson 하드웨어 모니터 (CPU / GPU / RAM)
│   ├── pipeline_lifecycle.py   # 파이프라인 생성·해제·재시작
│   ├── clip_storage.py         # 디스크 여유 공간 관리 + 오래된 클립 정리
│   ├── trigger_clip_rollover.py # 세그먼트 롤오버 기반 클립 녹화
│   ├── trigger_clip_diagnostics.py # 클립 메타데이터 + 진단 정보
│   ├── ptz.py                  # ONVIF PTZ 제어
│   ├── holder.py               # VLM 모델 싱글턴 홀더
│   ├── vlm_worker.py           # VLM 추론 서브프로세스 (모델 전환 시 CUDA/TVM/TensorRT 메모리 회수)
│   └── server_support.py       # 서버 보조 헬퍼 (JWT 검증, 클립 경로 해석, Range 파싱)
├── api/                        # API 서버 소스
│   ├── main.py                 # FastAPI 엔드포인트
│   ├── auth.py                 # JWT 인증 + 로그인 스로틀 + 리프레시 토큰 라이프사이클
│   ├── app_proxy.py            # App 카메라 프로파일 프록시
│   ├── clip_support.py         # 클립 경로 해석 + Range 헤더 파싱 헬퍼
│   ├── database.py             # SQLite (WAL) 초기화
│   └── schemas.py              # Pydantic 스키마
├── web/                        # 웹 대시보드 (Vue 3 + Vite)
│   ├── docker-compose.yml      # 독립 Compose 스택
│   └── src/
│       ├── views/              # LoginView, DashboardView
│       ├── components/         # LiveStream, ClipsPanel, CameraPanel, PromptPanel, PtzOverlay, SystemOverlay, LiveStreamSystemPanel …
│       ├── composables/        # useAuth, useCamera, useClips, useSSE, usePtz, useTheme, useFetch, useLocale …
│       └── i18n/               # 한국어·영어 로케일
├── config/                     # 런타임 설정 (cam_profile.json, mediamtx.yml)
├── data/
│   ├── {YYYY}/{MM}/            # 트리거 클립 (*.mp4 + *.json 사이드카)
│   ├── db/                     # SQLite 데이터베이스 (users, events, devices)
│   └── models/                 # 모델 캐시 (MLC 컴파일 `.so`, HuggingFace 스냅샷, clip_trt TensorRT 엔진)
├── docker/                     # 메인 스택 Dockerfile (app, api)
├── tests/                      # 테스트 모음 (API, 파이프라인, 하드웨어, VLM 벤치마크)
├── docs/                       # API 레퍼런스 + 아키텍처 경계 문서
└── docker-compose.yml          # 메인 스택 (app + mediamtx + api)
```

## 기술 스택

| 영역 | 선택 |
|---|---|
| VLM 추론 | NanoLLM + VILA1.5-3b (MLC, INT4 양자화) |
| 비디오 파이프라인 | GStreamer + nvv4l2decoder (GPU 하드웨어 디코딩) |
| 스트리밍 | MediaMTX (RTSP / HLS / WebRTC) |
| 알림 | FCM HTTP v1 API (OAuth 2.0) |
| API 서버 | FastAPI + SQLite (WAL) |
| 인증 | JWT 액세스 토큰 + 리프레시 토큰 (HMAC-SHA256, PBKDF2 패스워드 해싱) |
| 웹 대시보드 | Vue 3 + Vite + Vue Router |
| PTZ 제어 | ONVIF SOAP (WS-Security) |

## API 개요

### App (:8080)

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 헬스 체크 |
| GET | `/events` | SSE (실시간 추론 결과 + 하드웨어 상태) |
| GET | `/stream` | MJPEG 스트림 (VLM 입력 프레임) |
| GET | `/camera` | 카메라 설정 조회 |
| POST | `/camera` | 카메라 설정 적용 (변경 시 GStreamer 파이프라인 재시작) |
| POST | `/prompt` | VLM 프롬프트 / 트리거 키워드 갱신 |
| POST | `/ptz` | PTZ 제어 (move / stop / save / goto) |
| POST | `/vlm/switch` | VLM 모델 전환 요청 |
| GET | `/clips` | 클립 목록 조회 |
| GET | `/clip/{name}` | 클립 다운로드 (Range 지원) |
| DELETE | `/clips` | 선택 클립 삭제 (`.json` 사이드카 함께 삭제) |

`/stream`과 `/events`는 `Authorization` 헤더를 설정할 수 없는 클라이언트(예: `EventSource`)를 위해 `?token=<jwt>` 쿼리 파라미터도 허용합니다.

### API Server (:8000)

| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/login` | 불필요 | 로그인 (JWT 반환) |
| POST | `/api/refresh` | 불필요 | 리프레시 토큰 교체 + 새 액세스 토큰 발급 |
| POST | `/api/logout` | 불필요 | 리프레시 토큰 폐기 |
| POST | `/api/change-password` | 필요 | 비밀번호 변경 |
| GET | `/health` | 불필요 | 헬스 체크 |
| GET | `/camera` | 필요 | 카메라 프로파일 조회 (App 프록시) |
| POST | `/camera` | 필요 | 카메라 프로파일 적용 (App 프록시) |
| GET | `/clips` | 필요 | 클립 목록 |
| GET | `/clips/{name}` | 필요 | 클립 다운로드 (Range 지원) |
| DELETE | `/clips` | 필요 | 선택 클립 삭제 |
| DELETE | `/clips/all` | 필요 | 전체 클립 삭제 |
| GET/POST/DELETE | `/events` | 필요 | 이벤트 이력 CRUD |
| GET/POST | `/devices` | 필요 | FCM 디바이스 토큰 관리 |
| DELETE | `/devices/{device_id}` | 필요 | 디바이스 토큰 삭제 |

전체 스키마 레퍼런스: [docs/api.md](docs/api.md)

아키텍처 경계 가이드: [docs/architecture-boundaries.md](docs/architecture-boundaries.md)

## 환경 변수

### 공통

| 변수 | 기본값 | 설명 |
|---|---|---|
| `JWT_SECRET` | `babycat-default-secret` | JWT 서명 키 (App과 API 컨테이너 간 동일해야 함) |
| `HOST_IP` | — | MediaMTX가 WebRTC ICE 후보로 광고할 호스트 IP. 복수 IP는 쉼표로 구분 |

### App

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://mtx:8554/live` | MediaMTX RTSP URL (Compose 서비스명 `mtx`) |
| `VLM_MODELS` | `Efficient-Large-Model/VILA1.5-3b` | 쉼표 구분 VLM 모델 ID 목록. 첫 번째가 부팅 기본값 |
| `TARGET_FPS` | `1.0` | 프레임 샘플링 FPS |
| `N_FRAMES` | `4` | 추론 1회당 프레임 수 |
| `RING_SIZE` | `30` | 링 버퍼 크기 (프레임) |
| `TRIGGER_COOLDOWN` | `30` | 트리거 클립 최소 간격 (초) |
| `TRIGGER_CLIP_DUR` | `5` | 트리거 클립 길이 (초) |
| `CLIP_MIN_FREE_MB` | `256` | 클립 녹화 전 최소 여유 디스크 (MB) |
| `CLIP_TARGET_FREE_MB` | `512` | 공간 확보 정리 목표 여유량 (MB) |
| `CLIP_PRUNE_MAX_FILES` | `20` | 1회 정리 패스당 최대 삭제 클립 수 |
| `CONFIG_PATH` | `/config/cam_profile.json` | 카메라 프로파일 파일 경로 |
| `DATA_DIR` | `/data` | 트리거 클립 기본 디렉터리 (`{YYYY}/{MM}/` 하위 생성) |
| `FCM_CREDENTIALS` | — | FCM 서비스 계정 JSON 파일 경로 |
| `FCM_TOKEN` | — | 대상 디바이스 FCM 토큰 |
| `TRIGGER_ROLLOVER_ENABLED` | `0` | `1`로 설정 시 세그먼트 롤오버 기반 클립 녹화 활성화 |
| `TRIGGER_SEGMENT_DIR` | `/run/babycat-segments/live` | 롤오버 세그먼트 임시 저장 디렉터리 (tmpfs 권장) |

### API Server

| 변수 | 기본값 | 설명 |
|---|---|---|
| `CAM_DIR` | `/data` | 클립 조회 기준 디렉터리 (App의 `DATA_DIR`과 동일 볼륨) |
| `DB_PATH` | `/data/db/babycat.db` | SQLite 데이터베이스 경로 |
| `JWT_EXPIRY` | `600` | 액세스 토큰 유효 시간 (초) |
| `REFRESH_EXPIRY` | `2592000` | 리프레시 토큰 유효 시간 (초) |
| `DEFAULT_USER` | `admin` | 최초 부팅 시 생성되는 관리자 계정 이름 |
| `DEFAULT_PASS` | `admin` | 최초 부팅 시 생성되는 관리자 비밀번호 |
| `BABYCAT_APP_URL` | `http://app:8080` | 카메라 프록시가 사용하는 App 내부 URL (Compose 서비스명 `app`) |
| `CORS_EXTRA_ORIGINS` | — | API 서버에 추가 허용할 CORS 오리진 |

## 알려진 제한 사항

| 항목 | 내용 |
|---|---|
| VLM 추론 지연 | Jetson Orin NX 16 GB 기준: 1프레임 ~1700 ms, 4프레임 ~4200 ms. 16 GB 보드에서는 CLIP TensorRT 내부 임계값(20 GB) 미달로 Transformers 폴백이 적용됨 |
| VLM 출력 형식 | VILA1.5-3b는 `DETECTED:XX` 같은 엄격한 출력 양식을 일관되게 따르지 않음. 자유 형식 생성 후 트리거 키워드 매칭 방식이 실제로 더 안정적 |
| 컨테이너 GPU 디코딩 | 컨테이너 내부에서 `nvv4l2decoder`를 사용하려면 `kmod` 패키지가 필요함. `lsmod`가 없으면 GStreamer가 `cuvidv4l2`로 폴백하는데, Jetson iGPU에서는 이 경로가 실패함 |

## 라이선스
GNU General Public License v3.0 (GPL-3.0)

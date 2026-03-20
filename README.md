# 왈리 (Wally)

반려견 이상 행동 실시간 감지 시스템

반려견이 펫하우스 내부에 혼자 있는 동안 발생할 수 있는 이상 행동을 24시간 실시간으로 감지하여 견주의 스마트폰에 즉시 알림을 전달한다. 견주는 앱에서 펫하우스 영상을 실시간으로 확인할 수 있다.

---

## 레포지토리 구성

```
wally/
├── backend/   # Jetson 엣지 AI 서버 — GStreamer + VLM 추론 + FCM 알림
└── frontend/  # Android 앱 — Vue 3 + Capacitor
```

| 디렉토리 | 설명 | 문서 |
|---|---|---|
| [`backend/`](backend/) | NVIDIA Jetson Orin NX에서 실행되는 엣지 AI 서버 | [README](backend/README-backend.md) |
| [`frontend/`](frontend/) | Android 네이티브 앱 (Vue 3 + Capacitor) | [README](frontend/README-frontend.md) |

---

## 시스템 개요

### 하드웨어

| 구성 요소 | 사양 |
|---|---|
| Edge AI 보드 | NVIDIA Jetson Orin NX 16GB |
| 카메라 | IR 지원 IP Camera (RTSP, H.264) |
| 클라이언트 | Android 스마트폰 |

### 감지 대상 행동 (Phase 1 — 시각 기반)

발작 · 구토 · 헛구역질 · 긁기 · 선회운동 · 과다 핥기 · 과다 헐떡임

### 파이프라인 구조

```
IP Camera (RTSP)
   │
   ├─ Branch A ── MediaMTX ──────────────────────── Android 앱 (실시간 스트리밍)
   │                  │
   │              세그먼트 녹화 (순환)
   │
   └─ Branch B ── GStreamer (GPU 디코딩) ── VLM 추론 (VILA1.5-3b)
                                                │
                                           이상 감지
                                                │
                                    ┌───────────┴───────────┐
                               클립 보존                  FCM 알림
                           (MediaMTX 세그먼트)         (Android 앱)
```

- **Branch A**: MediaMTX가 카메라 RTSP를 직접 pull → 앱에 재배포. AI 분석 지연과 완전히 격리
- **Branch B**: GStreamer가 MediaMTX에서 읽어 GPU 디코딩(`nvv4l2decoder`) → VLM 추론 → 이벤트 판정

---

## Backend

**위치**: [`backend/`](backend/)
**실행 환경**: NVIDIA Jetson Orin NX (JetPack 6.2, Docker)

### 컨테이너 구성

| 컨테이너 | 포트 | 역할 |
|---|---|---|
| `mediamtx` | 8554 (RTSP) · 8888 (HLS) · 8889 (WebRTC) | 스트리밍 서버 |
| `wally-backend-app` | 8080 (디버그 UI) | GStreamer · VLM 추론 · FCM 발송 |
| `wally-backend-api` | 8000 (REST) | 기기 토큰 등록 · 이벤트 이력 · 클립 제공 |

### 빠른 시작

```bash
cd backend

# 이미지 빌드 (최초 1회)
docker compose build app

# 컨테이너 실행
docker compose up -d

# 디버그 대시보드 확인
open http://localhost:8080
```

### FCM 알림 활성화

1. Firebase Console에서 서비스 계정 JSON 키 발급 → `backend/config/fcm_credentials.json` 저장
2. `docker-compose.yml`에서 `FCM_CREDENTIALS`, `FCM_TOKEN` 주석 해제

---

## Frontend

**위치**: [`frontend/`](frontend/)
**타겟**: Android (앱 ID: `com.wally.app`)
**스택**: Vue 3 · Vite · Capacitor 8

### 화면 구성

| 경로 | 화면 | 주요 컴포넌트 |
|---|---|---|
| `/home` | 홈 | 실시간 영상(CamView) · 카메라 상태(StateBar) · PTZ 조작(CamBar) |
| `/alarm` | 알람 | 이상 감지 이벤트 이력 |
| `/schedule` | 스케줄 | 예약 기능 |
| `/settings` | 설정 | 앱 설정 |

### 빠른 시작

```bash
cd frontend

# 의존성 설치
npm install

# 웹 개발 서버 실행
npm run dev

# Android 빌드
npm run build
npx cap sync android
npx cap open android   # Android Studio에서 열기
```

**Node 요구 사항**: `^20.19.0` 또는 `>=22.12.0`

---

## 개발 현황

| 항목 | 상태 |
|---|---|
| GStreamer 파이프라인 (GPU 디코딩) | ✅ 완료 |
| VLM 추론 (VILA1.5-3b, ~4200ms/추론) | ✅ 완료 |
| 이벤트 판정 로직 | ✅ 완료 |
| FCM 알림 (stub) | ✅ 완료 (실 credentials 설정 시 활성화) |
| 영상 클립 보존 (MediaMTX 세그먼트) | ✅ 완료 |
| E2E 통합 테스트 | ✅ 12/12 PASS |
| ONVIF PTZ 제어 | ✅ 완료 |
| 디버그 대시보드 (MJPEG · SSE · PTZ) | ✅ 완료 |
| Android 앱 UI 뼈대 | 🔧 진행 중 |
| 앱 ↔ 백엔드 API 연동 | ⬜ 예정 |
| HLS 실시간 스트리밍 (앱 연결) | ⬜ 예정 |
| 청각 감지 (Phase 2) | ⬜ 예정 |

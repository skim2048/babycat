# Babycat — API 레퍼런스

> **버전**: v0.2
> **인코딩**: UTF-8, JSON

---

## 목차

1. [서비스 구조](#1-서비스-구조)
2. [실시간 스트리밍](#2-실시간-스트리밍)
3. [시스템 상태 (SSE)](#3-실시간-상태-sse)
4. [VLM 제어](#4-vlm-제어)
5. [PTZ 카메라 제어](#5-ptz-카메라-제어)
6. [클립 관리](#6-클립-관리)
7. [이벤트 이력](#7-이벤트-이력)
8. [기기 토큰](#8-기기-토큰)
9. [헬스체크](#9-헬스체크)
10. [공통 사항](#10-공통-사항)

---

## 1. 서비스 구조

프론트엔드는 **3개의 서비스**와 통신해야 한다. 모두 같은 Jetson 호스트에서 실행된다.

![서비스 구조](diagram.svg)

| 서비스 | 포트 | 용도 | 프로토콜 |
|---|---|---|---|
| **MediaMTX** | 8888 | 라이브 영상 스트리밍 | HLS (HTTP) |
| **App** | 8080 | 시스템 상태, VLM 제어, PTZ 제어, VLM 입력 프레임 | HTTP (SSE, MJPEG, JSON) |
| **API Server** | 8000 | 클립 파일, 이벤트 이력, 기기 토큰 | HTTP (REST, JSON) |

### 인증

현재 없음. Android 앱 연동 단계에서 추가 검토.

### CORS

현재 미설정. 프론트엔드가 다른 origin에서 호출하는 경우 별도 설정 필요.

---

## 2. 실시간 스트리밍

### 라이브 영상 (HLS)

카메라 실시간 영상. MediaMTX가 IP 카메라에서 직접 pull하여 HLS로 변환한다.

**URL**: `http://<host>:8888/live/index.m3u8`

**프론트엔드 사용법** (hls.js):

```html
<video id="live" autoplay muted></video>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
const video = document.getElementById('live');
if (Hls.isSupported()) {
  const hls = new Hls();
  hls.loadSource('http://<host>:8888/live/index.m3u8');
  hls.attachMedia(video);
}
</script>
```

> Safari는 `<video src="...m3u8">` 네이티브 지원. 그 외 브라우저는 hls.js 필요.

---

### VLM 입력 프레임 (MJPEG)

VLM에 입력되는 384x384 리사이즈 프레임. 디버깅/모니터링 용도.

**URL**: `http://<host>:8080/stream`

**프론트엔드 사용법**:

```html
<img src="http://<host>:8080/stream" />
```

> MJPEG는 `<img>` 태그에 직접 연결하면 브라우저가 자동으로 프레임을 갱신한다. `<video>` 태그가 아님에 주의.
> 주의: `<img src>`를 HTML에 직접 넣으면 페이지 로딩 스피너가 계속 돈다. `window.onload` 이후 JS로 src를 설정할 것.

---

## 3. 시스템 상태 (SSE; Server-Sent Events)

### `GET http://<host>:8080/events`

Server-Sent Events로 추론 결과, 하드웨어 상태, 파이프라인 상태를 실시간 수신한다. 약 2초 간격으로 업데이트된다.

**프론트엔드 사용법**:

```javascript
const es = new EventSource('http://<host>:8080/events');
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log(data);
};
```

**SSE `data` 필드 스키마**:

```json
{
  "frame_w": 1920,
  "frame_h": 1080,
  "infer_label": "person detected",
  "infer_raw": "I can see a person standing near the door.",
  "infer_ms": 1723.4,

  "cpu_percent": 45.2,
  "ram_used_mb": 8234,
  "ram_total_mb": 15700,
  "gpu_load": 62.3,
  "cpu_temp": 51.2,
  "gpu_temp": 53.8,

  "ring_len": 4,
  "ring_size": 30,
  "judge_streak": "person (2/3)",
  "uptime": "1h 23m 45s",

  "ptz_pan": 0.220,
  "ptz_tilt": -0.553,
  "ptz_saved_pan": 0.220,
  "ptz_saved_tilt": -0.553,

  "inference_prompt": "Describe what you see.",
  "trigger_keywords": "person,fire",
  "event_triggered": false,
  "clip_count": 5,

  "cfg_TARGET_FPS": 1,
  "cfg_N_FRAMES": 4,
  "cfg_CONSEC_N": 3
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `frame_w`, `frame_h` | int | 원본 프레임 해상도 |
| `infer_label` | string | 추론 결과 라벨 |
| `infer_raw` | string | VLM 원문 응답 |
| `infer_ms` | float | 추론 소요 시간 (ms) |
| `cpu_percent` | float | CPU 사용률 (%) |
| `ram_used_mb`, `ram_total_mb` | int | RAM 사용량/총량 (MB) |
| `gpu_load` | float | GPU 사용률 (%) |
| `cpu_temp`, `gpu_temp` | float | CPU/GPU 온도 (C) |
| `ring_len` | int | 현재 Ring Buffer에 있는 프레임 수 |
| `ring_size` | int | Ring Buffer 최대 크기 |
| `judge_streak` | string | 연속 감지 상태 (예: `"person (2/3)"`, 비어있으면 `""`) |
| `uptime` | string | App 컨테이너 가동 시간 |
| `ptz_pan`, `ptz_tilt` | float \| null | 현재 PTZ 위치 (-1.0 ~ 1.0) |
| `ptz_saved_pan`, `ptz_saved_tilt` | float \| null | 저장된 홈 위치 |
| `inference_prompt` | string | 현재 VLM 프롬프트 |
| `trigger_keywords` | string | 현재 트리거 키워드 (쉼표 구분) |
| `event_triggered` | bool | 직전 추론에서 이벤트가 감지되었는지 |
| `clip_count` | int | 현재 클립 파일 수 |
| `cfg_*` | any | 파이프라인 설정값 (접두사 `cfg_`) |

---

## 4. VLM 제어

### `POST http://<host>:8080/prompt`

VLM 추론에 사용할 프롬프트와 이벤트 트리거 키워드를 변경한다.

**Request Body**:

```json
{
  "prompt": "Describe what you see in the image.",
  "triggers": "person, fire, smoke"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `prompt` | string | 필수 | VLM에 전달할 사전 프롬프트 |
| `triggers` | string | 선택 | 쉼표로 구분된 트리거 키워드. VLM 응답에 키워드가 포함되면 이벤트 발생 |

**Response `200`**:

```json
{
  "ok": true
}
```

**동작 방식**:
- `prompt`가 비어있으면 기존 프롬프트 유지
- `triggers`가 비어있으면 트리거 비활성화 (이벤트 감지 안 함)
- 변경 즉시 다음 추론부터 적용
- 현재 값은 SSE의 `inference_prompt`, `trigger_keywords` 필드로 확인 가능

---

## 5. PTZ 카메라 제어

### `POST http://<host>:8080/ptz`

카메라 Pan/Tilt 제어. ONVIF 프로토콜로 카메라에 직접 명령한다.

**Request Body** — `action` 필드에 따라 분기:

#### `move` — 연속 이동 시작

버튼을 누르고 있는 동안 호출. 놓으면 `stop`을 보내야 한다.

```json
{
  "action": "move",
  "pan": 0.5,
  "tilt": 0.0
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `pan` | float | 좌(-) / 우(+) 속도. -1.0 ~ 1.0 |
| `tilt` | float | 하(-) / 상(+) 속도. -1.0 ~ 1.0 |

#### `stop` — 이동 정지

```json
{
  "action": "stop"
}
```

#### `save` — 현재 위치를 홈으로 저장

```json
{
  "action": "save"
}
```

#### `goto` — 저장된 홈 위치로 이동

```json
{
  "action": "goto"
}
```

**Response `200`** (모든 action 공통):

```json
{
  "ok": true
}
```

`ok: false` — `save` 시 현재 위치를 아직 수신하지 못한 경우, `goto` 시 저장된 위치가 없는 경우.

**현재 위치 확인**: SSE의 `ptz_pan`, `ptz_tilt` 필드 (2초 폴링).

---

## 6. 클립 관리

> Base URL: `http://<host>:8000`

클립 파일은 이벤트 감지 시 App 컨테이너가 ffmpeg로 RTSP 스트림에서 5초간 녹화한 mp4 파일이다.

> 10KB 미만 파일은 녹화 중인 불완전한 파일로 간주하여 목록에서 제외된다.

### 데이터 모델

```json
{
  "name": "event_20260326_153012.mp4",
  "size": 2457600,
  "created_at": "2026-03-26T15:30:12Z"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | 파일명 (고유 식별자) |
| `size` | int | 바이트 단위 파일 크기 |
| `created_at` | string (ISO 8601) | 파일 생성 시각 (UTC) |

---

### `GET /clips`

클립 목록 조회. 최신순 정렬.

**Query Parameters**:

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `q` | string | 선택 | 파일명 키워드 필터 (부분 일치) |
| `limit` | int | 선택 | 최대 반환 개수. 기본값 100 |
| `offset` | int | 선택 | 페이지네이션 오프셋. 기본값 0 |

**Response `200`**:

```json
{
  "clips": [
    {
      "name": "event_20260326_153012.mp4",
      "size": 2457600,
      "created_at": "2026-03-26T15:30:12Z"
    }
  ],
  "total": 1
}
```

---

### `GET /clips/{name}`

클립 파일 다운로드. 브라우저 `<video>` 재생을 위한 Range 요청을 지원한다.

**프론트엔드 사용법**:

```html
<video src="http://<host>:8000/clips/event_20260326_153012.mp4" controls></video>
```

| 상태 코드 | 설명 |
|---|---|
| `200` | 전체 파일 (`Content-Type: video/mp4`) |
| `206` | 부분 콘텐츠 (Range 요청, 브라우저가 자동으로 보냄) |
| `404` | 파일 없음 |

---

### `DELETE /clips`

선택 삭제. 파일명 배열로 지정한 클립만 삭제한다.

**Request Body**:

```json
{
  "names": ["event_20260326_153012.mp4", "event_20260326_160000.mp4"]
}
```

`names`가 빈 배열이면 아무것도 삭제하지 않는다.

**Response `200`**:

```json
{
  "deleted": 2
}
```

---

### `DELETE /clips/all`

전체 삭제. 클립 디렉토리의 모든 mp4 파일을 삭제한다.

**Response `200`**:

```json
{
  "deleted": 15
}
```

---

## 7. 이벤트 이력

> Base URL: `http://<host>:8000`

App 컨테이너가 이벤트 감지 시 이 API를 호출하여 이력을 기록한다. 프론트엔드는 이력을 조회/삭제한다.

### 데이터 모델

```json
{
  "id": 1,
  "trigger": "person detected",
  "clip_name": "event_20260326_153012.mp4",
  "created_at": "2026-03-26T15:30:12Z"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | int | 자동 증가 PK |
| `trigger` | string | 감지된 트리거 키워드 |
| `clip_name` | string \| null | 연결된 클립 파일명. 없으면 null |
| `created_at` | string (ISO 8601) | 이벤트 발생 시각 (UTC) |

---

### `GET /events`

이벤트 이력 조회. 최신순 정렬.

**Query Parameters**:

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `limit` | int | 선택 | 최대 반환 개수. 기본값 50 |
| `offset` | int | 선택 | 페이지네이션 오프셋. 기본값 0 |

**Response `200`**:

```json
{
  "events": [
    {
      "id": 1,
      "trigger": "person detected",
      "clip_name": "event_20260326_153012.mp4",
      "created_at": "2026-03-26T15:30:12Z"
    }
  ],
  "total": 1
}
```

---

### `POST /events`

이벤트 기록. **App 컨테이너가 호출** (주의: 프론트엔드에서 호출하지 말 것).

**Request Body**:

```json
{
  "trigger": "person detected",
  "clip_name": "event_20260326_153012.mp4"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `trigger` | string | 필수 | 감지된 트리거 키워드 |
| `clip_name` | string | 선택 | 연결할 클립 파일명 |

**Response `201`**:

```json
{
  "id": 1,
  "trigger": "person detected",
  "clip_name": "event_20260326_153012.mp4",
  "created_at": "2026-03-26T15:30:12Z"
}
```

---

### `DELETE /events`

이벤트 이력 전체 삭제.

**Response `200`**:

```json
{
  "deleted": 42
}
```

---

## 8. 기기 토큰

> Base URL: `http://<host>:8000`

Android 앱이 FCM 토큰을 등록·갱신한다. App 컨테이너는 이벤트 발생 시 등록된 모든 토큰에 FCM 푸시 알림을 발송한다.

### 데이터 모델

```json
{
  "id": 1,
  "fcm_token": "fGH3k...",
  "label": "my-phone",
  "registered_at": "2026-03-26T10:00:00Z"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | int | 자동 증가 PK |
| `fcm_token` | string | FCM 기기 토큰 (고유) |
| `label` | string \| null | 기기 별칭 (선택) |
| `registered_at` | string (ISO 8601) | 등록 시각 (UTC) |

---

### `GET /devices`

등록된 기기 목록 조회.

**Response `200`**:

```json
{
  "devices": [
    {
      "id": 1,
      "fcm_token": "fGH3k...",
      "label": "my-phone",
      "registered_at": "2026-03-26T10:00:00Z"
    }
  ]
}
```

---

### `POST /devices`

기기 토큰 등록 또는 갱신. `fcm_token`이 이미 존재하면 `label`만 갱신한다 (upsert).

**Request Body**:

```json
{
  "fcm_token": "fGH3k...",
  "label": "my-phone"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `fcm_token` | string | 필수 | FCM 기기 토큰 |
| `label` | string | 선택 | 기기 별칭 |

**Response `200`**:

```json
{
  "id": 1,
  "fcm_token": "fGH3k...",
  "label": "my-phone",
  "registered_at": "2026-03-26T10:00:00Z"
}
```

---

### `DELETE /devices/{id}`

기기 토큰 삭제.

**Response `200`**:

```json
{
  "deleted": 1
}
```

| 상태 코드 | 설명 |
|---|---|
| `200` | 삭제 성공 |
| `404` | 해당 ID의 기기 없음 |

---

## 9. 헬스체크

### `GET http://<host>:8000/health`

API 서버 상태 확인.

**Response `200`**:

```json
{
  "status": "ok"
}
```

---

## 10. 공통 사항

### 에러 응답

모든 에러는 아래 형식을 따른다 (API 서버, `:8000`).

```json
{
  "detail": "clip not found"
}
```

| 상태 코드 | 의미 |
|---|---|
| `400` | 잘못된 요청 (경로 탈출 시도 등) |
| `404` | 리소스 없음 |
| `422` | 요청 바디 유효성 실패 (FastAPI 기본) |
| `500` | 서버 내부 오류 |

### 엔드포인트 전체 목록

| 서비스 | 메서드 | 경로 | 설명 |
|---|---|---|---|
| MediaMTX :8888 | GET | `/live/index.m3u8` | HLS 라이브 스트림 |
| App :8080 | GET | `/stream` | MJPEG (VLM 입력 프레임) |
| App :8080 | GET | `/events` | SSE (시스템 상태) |
| App :8080 | POST | `/prompt` | VLM 프롬프트/트리거 변경 |
| App :8080 | POST | `/ptz` | PTZ 카메라 제어 |
| API :8000 | GET | `/health` | 헬스체크 |
| API :8000 | GET | `/clips` | 클립 목록 |
| API :8000 | GET | `/clips/{name}` | 클립 파일 다운로드 |
| API :8000 | DELETE | `/clips` | 클립 선택 삭제 |
| API :8000 | DELETE | `/clips/all` | 클립 전체 삭제 |
| API :8000 | GET | `/events` | 이벤트 이력 조회 |
| API :8000 | POST | `/events` | 이벤트 기록 (App 전용) |
| API :8000 | DELETE | `/events` | 이벤트 이력 전체 삭제 |
| API :8000 | GET | `/devices` | 기기 목록 |
| API :8000 | POST | `/devices` | 기기 등록/갱신 |
| API :8000 | DELETE | `/devices/{id}` | 기기 삭제 |

### 컨테이너 구성

```yaml
api:
  build:
    context: .
    dockerfile: docker/api/Dockerfile
  container_name: babycat-api
  restart: unless-stopped
  ports:
    - "8000:8000"
  environment:
    - CLIP_DIR=/data/clips
    - DB_PATH=/data/db/babycat.db
  volumes:
    - ./app/clip:/data/clips        # 클립 서빙 및 삭제 (읽기-쓰기)
    - api_data:/data/db             # SQLite 데이터베이스
  depends_on:
    - app
```

> **클립 공유**: App 컨테이너는 `./app:/app` bind mount를 통해 `/app/clip`에 클립을 쓴다. API 서버는 같은 호스트 경로(`./app/clip`)를 `/data/clips`로 마운트하여 읽기/삭제한다.

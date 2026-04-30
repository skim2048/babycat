# Babycat — API 레퍼런스

> **버전**: v0.3
> **인코딩**: UTF-8, JSON

---

## 목차

1. [서비스 구조](#1-서비스-구조)
2. [인증](#2-인증)
3. [실시간 스트리밍](#3-실시간-스트리밍)
4. [시스템 상태 (SSE)](#4-시스템-상태-sse)
5. [VLM 제어](#5-vlm-제어)
6. [PTZ 카메라 제어](#6-ptz-카메라-제어)
7. [카메라 프로파일](#7-카메라-프로파일)
8. [클립 관리](#8-클립-관리)
9. [이벤트 이력](#9-이벤트-이력)
10. [기기 토큰](#10-기기-토큰)
11. [헬스체크](#11-헬스체크)
12. [공통 사항](#12-공통-사항)

---

## 1. 서비스 구조

프론트엔드는 **3개의 서비스**와 통신해야 한다. 모두 같은 Jetson 호스트에서 실행된다.

| 서비스 | 포트 | 용도 | 프로토콜 |
|---|---|---|---|
| **MediaMTX** | 8554 / 8888 / 8889 / 8890/udp | 라이브 영상 (RTSP 수신, HLS/WebRTC 송출) | RTSP · HLS · WebRTC |
| **App** | 8080 | 시스템 상태, VLM 제어, PTZ 제어, 카메라 프로파일, VLM 입력 프레임 | HTTP (SSE, MJPEG, JSON) |
| **API Server** | 8000 | 인증, 클립 파일, 이벤트 이력, 기기 토큰, 카메라 프로파일(프록시) | HTTP (REST, JSON) |

### CORS

**API Server(:8000)**는 CORS를 활성화한다. 허용 origin은 localhost/127.0.0.1, 사설 IP 대역(10.*, 172.16~31.*, 192.168.*), `capacitor://localhost`이며, `allow_credentials=False`다. 외부 도메인에서 접근할 경우 `CORS_EXTRA_ORIGINS` 환경변수에 콤마로 나열한다.

**App(:8080)**에는 CORS 미들웨어가 없으므로 동일 origin에서 호출하거나 프록시를 경유해야 한다.

---

## 2. 인증

모든 보호된 엔드포인트는 **JWT (HS256)** 토큰을 요구한다. 두 컨테이너는 동일한 `JWT_SECRET` 환경변수를 공유한다.

**면제되는 경로**: `GET :8080/` (App 헬스), `GET :8000/health` (API 헬스), `POST :8000/api/login`, `POST :8000/api/refresh`, `POST :8000/api/logout` (리프레시 토큰 자체가 자격증명이므로 액세스 토큰 검증을 건너뜁니다).

### 토큰 전달 방식

| 방식 | 지원 서비스 | 사용처 |
|---|---|---|
| `Authorization: Bearer <token>` | App, API | 일반 REST 호출 |
| `?token=<token>` 쿼리 파라미터 | App, API (일부 예외 있음) | 브라우저 `EventSource`, `<img>`/`<video>` 등 헤더를 설정할 수 없는 클라이언트. API 서버의 `require_auth`도 Authorization 헤더가 없으면 동일 쿼리 파라미터를 인식합니다. 단, API 서버의 `/camera` 프록시는 내부 App 호출에 `Authorization` 헤더만 전달하므로 현재는 Bearer 헤더를 사용해야 합니다 |

실패 응답:
- API 서버: `401 {"detail": "missing token"}` 또는 `401 {"detail": "invalid or expired token"}`
- App 서버: `401 {"detail": "unauthorized"}`

### `POST http://<host>:8000/api/login`

사용자명/비밀번호로 로그인한다. 세션 정책은 `remember_me`에 따라 갈린다. 기본 자격증명은 `docker-compose.yml`의 `DEFAULT_USER`/`DEFAULT_PASS` 환경변수로 설정된다.

**Request Body**:

```json
{
  "username": "admin",
  "password": "admin",
  "remember_me": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `username` | string | 필수 | |
| `password` | string | 필수 | |
| `remember_me` | bool | 선택 | `true`면 영속 세션, `false`면 비영속 세션. 기본값 `false` |

**Response `200`**:

```json
{
  "token": "eyJhbGciOi...",
  "expires_in": 600,
  "must_change_password": false,
  "refresh_token": "r_abc...",
  "refresh_expires_in": 2592000
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `token` | string | 액세스 토큰 (Bearer) |
| `expires_in` | int | 액세스 토큰 유효 시간 (초) |
| `must_change_password` | bool | 초기 비밀번호 상태. `true`면 로그인 직후 `/api/change-password` 호출 유도 |
| `refresh_token` | string | 영속 세션 자동 유지와 비영속 세션의 명시적 `연장`에 공통으로 사용되는 토큰 |
| `refresh_expires_in` | int | 위 토큰의 유효 시간 (초) |

세션 정책:

- `remember_me=true`: 영속 세션. `web`은 토큰을 `localStorage`에 저장하고, 세션 만료 경고 모달을 띄우지 않으며, 만료 전에 자동 갱신을 시도한다.
- `remember_me=false`: 비영속 세션. `web`은 토큰을 `sessionStorage`에 저장하고, 세션 만료 전에 경고 모달을 띄우며, 사용자가 `연장`을 눌렀을 때만 세션을 연장한다.

**Response `401`**: `{"detail": "invalid credentials"}`

### `POST http://<host>:8000/api/refresh`

세션 유지 또는 세션 연장 시 새 인증 정보를 발급한다. 현재 구현은 리프레시 토큰 회전 방식이지만, 최종 동작은 위 세션 정책을 만족해야 한다.

**Request Body**: `{ "refresh_token": "r_abc..." }`

**Response `200`**:

```json
{
  "token": "eyJhbGciOi...",
  "expires_in": 600,
  "refresh_token": "r_xyz...",
  "refresh_expires_in": 2592000
}
```

**Response `401`**: `{"detail": "invalid or expired refresh token"}`

### `POST http://<host>:8000/api/logout`

세션 유지 또는 연장에 사용되는 서버측 인증 수단을 폐기한다. 수동 로그아웃과 자동 로그아웃 모두 같은 정리 절차를 따르는 것을 정책 기준으로 본다. 액세스 토큰 검증은 건너뛰므로 이미 만료된 상태에서도 호출 가능하다.

**Request Body**: `{ "refresh_token": "r_abc..." }` 또는 `{}`. `refresh_token` 필드는 선택이지만 요청 바디 자체는 JSON 객체로 보내는 것이 안전하다.

**Response `200`**: `{"ok": true}`

### `POST http://<host>:8000/api/change-password`

인증 필수. 현재 비밀번호 검증 후 새 비밀번호로 교체.

**Request Body**: `{ "current_password": "...", "new_password": "..." }`

**Response `200`**: `{"ok": true}` — **Response `400`**: `{"detail": "current password is incorrect"}`

---

## 3. 실시간 스트리밍

### 라이브 영상 — HLS

카메라 실시간 영상. MediaMTX가 IP 카메라에서 RTSP로 pull하여 HLS로 변환한다. MediaMTX 자체 인증은 오픈 상태(내부 네트워크 전용 가정)이므로 HLS URL은 JWT 없이 접근 가능하다.

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

### 라이브 영상 — WebRTC

HLS 대비 지연이 낮다. 프론트엔드는 HLS/WebRTC 토글을 제공하며, 저장되는 값은 선호 전송 방식이다. 실제 연결 시도 중 선택한 방식이 실패하면 대시보드는 같은 연결 세션 안에서 다른 방식으로 한 번 폴백할 수 있다.

- **WHEP 엔드포인트**: `http://<host>:8889/live/whep`
- **ICE UDP**: `8890/udp` — MediaMTX는 `MTX_WEBRTCADDITIONALHOSTS` 환경변수로 전달된 `HOST_IP`를 ICE 후보로 광고한다 (docker-compose.yml의 `HOST_IP`가 반드시 설정되어야 외부 접속 가능).

### VLM 입력 프레임 (MJPEG)

VLM에 입력되는 384x384 리사이즈 프레임. 디버깅/모니터링 용도. **JWT 필수**이며, `<img>` 태그에서는 헤더를 설정할 수 없으므로 `?token=` 쿼리를 사용한다.

**URL**: `http://<host>:8080/stream?token=<JWT>`

```html
<img id="debug" />
<script>
window.addEventListener('load', () => {
  document.getElementById('debug').src = `http://<host>:8080/stream?token=${token}`;
});
</script>
```

> MJPEG는 `<img>` 태그에 직접 연결하면 브라우저가 자동으로 프레임을 갱신한다. `<video>` 태그가 아님에 주의.
> 주의: `<img src>`를 HTML에 직접 넣으면 페이지 로딩 스피너가 계속 돈다. `window.onload` 이후 JS로 src를 설정할 것.

---

## 4. 시스템 상태 (SSE; Server-Sent Events)

### `GET http://<host>:8080/events`

Server-Sent Events로 추론 결과, 하드웨어 상태, VLM 상태, 파이프라인 상태를 실시간 수신한다. 약 1초 간격으로 스냅샷을 송출한다. 여기의 파이프라인 상태는 `app`이 소유하는 GStreamer 실행 상태이며, 브라우저 재생 상태와는 별개다.

**인증**: JWT 필수. `EventSource`는 헤더를 못 넣으므로 `?token=` 쿼리를 사용한다.

**프론트엔드 사용법**:

```javascript
const es = new EventSource(`http://<host>:8080/events?token=${token}`);
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
  "pipeline_state": "streaming",
  "pipeline_state_detail": "",
  "pipeline_source_protocol": "rtsp",
  "pipeline_source_transport": "tcp",
  "pipeline_active_for_s": 100.0,
  "pipeline_last_frame_age_s": 0.4,
  "pipeline_restart_count": 2,
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
  "uptime": "1h 23m 45s",

  "ptz_pan": 0.220,
  "ptz_tilt": -0.553,
  "ptz_saved_pan": 0.220,
  "ptz_saved_tilt": -0.553,

  "inference_prompt": "Describe what you see.",
  "trigger_keywords": "person,fire",
  "event_triggered": false,
  "clip_count": 5,
  "clip_storage_state": "ok",
  "clip_storage_reason": "pruned_old_clips",
  "clip_storage_free_mb": 512,

  "vlm_state": "ready",
  "vlm_error": null,
  "vlm_models": ["Efficient-Large-Model/VILA1.5-3b"],
  "vlm_current_model": "Efficient-Large-Model/VILA1.5-3b",

  "cfg_TARGET_FPS": 1,
  "cfg_N_FRAMES": 4,
  "cfg_CONSEC_N": 3
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `frame_w`, `frame_h` | int | 원본 프레임 해상도 |
| `pipeline_state` | string | `app`이 소유하는 파이프라인 상태. 현재 `idle`, `starting`, `streaming`, `stalled`, `restarting`, `stopped`를 사용 |
| `pipeline_state_detail` | string | 현재 파이프라인 상태에 붙는 상세 맥락 값. 예: `waiting_for_vlm`, `waiting_for_camera`, `camera_apply`, `watchdog_timeout`, `shutdown`. `waiting_for_vlm`은 `vlm_state`가 `ready`가 아니면 비워진다 |
| `pipeline_source_protocol` | string | 현재 파이프라인 입력 프로토콜. 현재는 `rtsp` |
| `pipeline_source_transport` | string | 현재 파이프라인 입력 전송 방식. 현재는 `tcp` |
| `pipeline_active_for_s` | float \| null | 현재 파이프라인 시작 이후 경과 시간(초). 시작 전이면 `null` |
| `pipeline_last_frame_age_s` | float \| null | 마지막 프레임 수신 이후 경과 시간(초). 아직 프레임이 없으면 `null` |
| `pipeline_restart_count` | int | 앱 프로세스 시작 이후 파이프라인 재시작 횟수 |
| `infer_label` | string | 추론 결과 라벨 |
| `infer_raw` | string | VLM 원문 응답 |
| `infer_ms` | float | 추론 소요 시간 (ms) |
| `cpu_percent` | float | CPU 사용률 (%) |
| `ram_used_mb`, `ram_total_mb` | int | RAM 사용량/총량 (MB) |
| `gpu_load` | float | GPU 사용률 (%) |
| `cpu_temp`, `gpu_temp` | float | CPU/GPU 온도 (℃) |
| `ring_len` | int | 현재 Ring Buffer에 있는 프레임 수 |
| `ring_size` | int | Ring Buffer 최대 크기 |
| `uptime` | string | App 컨테이너 가동 시간 |
| `ptz_pan`, `ptz_tilt` | float \| null | 현재 PTZ 위치 (-1.0 ~ 1.0) |
| `ptz_saved_pan`, `ptz_saved_tilt` | float \| null | 저장된 홈 위치 |
| `inference_prompt` | string | 현재 VLM 프롬프트 |
| `trigger_keywords` | string | 현재 트리거 키워드 (쉼표 구분) |
| `event_triggered` | bool | 직전 추론에서 이벤트가 감지되었는지 |
| `clip_count` | int | 현재 클립 파일 수 |
| `clip_storage_state` | string | 최근 클립 저장 정책 결과. 현재 `ok`, `skipped`, `error`를 사용 |
| `clip_storage_reason` | string | 최근 클립 저장/정리 사유. 예: `pruned_old_clips`, `low_disk_space`, `ffmpeg_failed` |
| `clip_storage_free_mb` | int \| null | 최근 클립 저장 정책 판단 시점의 남은 디스크 공간 (MB) |
| `vlm_state` | string | VLM 상태 (`loading`, `ready`, `switching`, `error` 등) |
| `vlm_error` | string \| null | 오류 메시지 (있을 때) |
| `vlm_models` | string[] | 선택 가능한 VLM 모델 ID 목록 (`VLM_MODELS` 환경변수로 정의) |
| `vlm_current_model` | string | 현재 적재된 모델 ID |
| `cfg_*` | any | 파이프라인 설정값 (접두사 `cfg_`) |

---

## 5. VLM 제어

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
| `prompt` | string | 선택 | VLM에 전달할 사전 프롬프트. 비어있으면 기존 값 유지 |
| `triggers` | string | 선택 | 쉼표로 구분된 트리거 키워드. 비어있으면 트리거 비활성화 |

**Response `200`**: `{"ok": <bool>}` — `ok`는 `prompt`가 실제로 적용되었는지를 나타낸다(빈 문자열이면 `false`).

**동작 방식**:
- 변경 즉시 다음 추론부터 적용
- 현재 값은 SSE의 `inference_prompt`, `trigger_keywords` 필드로 확인 가능

### `POST http://<host>:8080/vlm/switch`

사용 가능한 모델 목록(SSE `vlm_models`) 중 하나로 VLM을 전환한다. 실제 전환은 다음 추론 루프 시작 시점에 수행된다.

**Request Body**: `{ "model": "Efficient-Large-Model/VILA1.5-3b" }`

**Response**:
- `200 {"ok": true, "reason": "..."}` — 전환 요청 접수
- `400 {"ok": false, "reason": "<사유>"}` — 모델명 누락 또는 목록에 없음

진행 상태는 SSE `vlm_state` / `vlm_current_model`로 관찰한다.

---

## 6. PTZ 카메라 제어

### `POST http://<host>:8080/ptz`

카메라 Pan/Tilt 제어. ONVIF 프로토콜로 카메라에 직접 명령한다.

**Request Body** — `action` 필드에 따라 분기:

#### `move` — 연속 이동 시작

버튼을 누르고 있는 동안 호출. 놓으면 `stop`을 보내야 한다.

```json
{ "action": "move", "pan": 0.5, "tilt": 0.0 }
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `pan` | float | 좌(-) / 우(+) 속도. 권장 범위 -1.0 ~ 1.0 |
| `tilt` | float | 하(-) / 상(+) 속도. 권장 범위 -1.0 ~ 1.0 |

`pan`/`tilt`를 float로 해석할 수 없으면 `400 invalid pan/tilt values`를 반환합니다. 값 범위 자체는 서버에서 검증하지 않으므로 호출자가 범위를 준수해야 합니다.

#### `stop` — 이동 정지

```json
{ "action": "stop" }
```

#### `save` — 현재 위치를 홈으로 저장

```json
{ "action": "save" }
```

홈으로 저장된 위치는 App 컨테이너의 카메라 프로파일 파일(`/config/cam_profile.json`, 호스트 `./config/cam_profile.json`) 안의 `ptz_home`에 영속 저장된다.

#### `goto` — 저장된 홈 위치로 이동

```json
{ "action": "goto" }
```

**Response `200`** (모든 action 공통): `{ "ok": <bool> }`

`ok: false` — `save` 시 현재 위치를 아직 수신하지 못한 경우, `goto` 시 저장된 위치가 없는 경우. 알 수 없는 `action` 값은 현재 구현상 거부되지 않고 `200 {"ok": true}`가 반환되므로, 클라이언트는 위 네 가지 값만 전송해야 합니다.

**현재 위치 확인**: SSE의 `ptz_pan`, `ptz_tilt` 필드.

---

## 7. 카메라 프로파일

카메라 입력원 프로파일을 관리한다. 현재 지원되는 입력원 종류는 `rtsp_camera` 하나이며, RTSP 연결 정보는 필수이고 ONVIF 제어 정보는 선택이다. 동일한 엔드포인트 두 개가 존재한다:

- **`:8000/camera` (API 서버)**: 프론트엔드에서 호출. 인증 후 내부적으로 `:8080/camera`로 프록시하며, 응답에서 password 원문을 제거하고 `password_set` 플래그만 남긴다. 현재 프록시 구현은 내부 App 호출에 `Authorization` 헤더만 전달하므로 이 엔드포인트는 `Authorization: Bearer <token>`로 호출해야 한다.
- **`:8080/camera` (App)**: API 서버가 내부 네트워크에서 호출하는 원본. 직접 호출도 가능하나 프론트엔드는 **:8000을 사용**할 것을 권장.

### `GET /camera`

**Response `200`**:

```json
{
  "configured": true,
  "source_type": "rtsp_camera",
  "ip": "192.168.1.10",
  "username": "admin",
  "password_set": true,
  "rtsp_port": 554,
  "onvif_port": null,
  "stream_path": "stream1",
  "ptz_home": { "pan": 0.22, "tilt": -0.553 }
}
```

미설정 상태: `{"configured": false}`

`ptz_home`가 존재하면 `{ "pan": number, "tilt": number }` 형태로 반환된다.

### `POST /camera`

카메라 프로파일을 적용한다. 성공 시 App 컨테이너는 RTSP 파이프라인 재시작을 비동기로 예약한다. 따라서 `{"ok": true}`는 프로파일 저장과 적용 경로가 성공했다는 뜻이며, 재시작 완료 자체를 동기적으로 보장하지는 않는다.

**Request Body**:

```json
{
  "source_type": "rtsp_camera",
  "ip": "192.168.1.10",
  "username": "admin",
  "password": "secret",
  "rtsp_port": 554,
  "onvif_port": null,
  "stream_path": "stream1"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `source_type` | string | 선택 | 현재는 `rtsp_camera`만 지원. 생략 시 기본값 `rtsp_camera` |
| `ip` | string | 필수 | 카메라 IP |
| `username` | string | 필수 | RTSP 사용자명. ONVIF를 사용할 경우에도 동일 자격증명을 사용 |
| `password` | string | 선택 | 생략 시 기존 비밀번호 유지 |
| `rtsp_port` | int | 선택 | 기본 554 |
| `onvif_port` | int \| null | 선택 | ONVIF PTZ 제어용 포트. `null` 또는 생략 시 PTZ를 비활성화 |
| `stream_path` | string | 선택 | RTSP path. 선행 슬래시 없이 전달 (기본값 `stream1`, URL 구성 시 `/` 뒤에 붙음) |
프로파일 파일 경로: App 컨테이너 내부 `/config/cam_profile.json` (환경변수 `CONFIG_PATH`로 변경 가능, docker-compose에서는 호스트 `./config` 디렉토리에 영속됩니다).

**Response `200`**: `{"ok": true}` 또는 `{"ok": false, "error": "<사유>"}`
**Response `502`**: App 컨테이너 접근 불가 (`{"detail": "upstream error"}`)

---

## 8. 클립 관리

> Base URL: `http://<host>:8000`

클립 파일은 이벤트 감지 시 App 컨테이너가 ffmpeg로 RTSP 스트림에서 5초간 녹화한 mp4 파일이다. 저장 구조는 `/data/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4`이며, 동일 이름의 `.json` 파일이 트리거 메타데이터(timestamp/keywords/vlm_text)를 담는다. 파일명의 날짜/시간은 컨테이너 로컬 timezone 기준이며, 현재 운영 기본값은 `Asia/Seoul`이다.

저장 전 App은 디스크 여유 공간을 확인한다. 여유 공간이 부족하면 오래된 클립부터 자동 정리한 뒤 다시 판단하며, 최소 여유 공간을 확보하지 못하면 새 클립 저장을 건너뛴다. 최근 판단 결과는 SSE의 `clip_storage_*` 필드로 노출된다.

기본 정책 환경변수:

- `CLIP_MIN_FREE_MB=256`: 이 값 미만이면 저장 전 정리 또는 저장 건너뜀
- `CLIP_TARGET_FREE_MB=512`: 자동 정리 시 이 값까지 회복을 시도
- `CLIP_PRUNE_MAX_FILES=20`: 한 번의 저장 시도에서 자동 삭제 가능한 최대 클립 수

> 10KB 미만 파일은 녹화 중인 불완전한 파일로 간주하여 목록에서 제외된다.

### 데이터 모델

```json
{
  "name": "20260326_153012_123.mp4",
  "size": 2457600,
  "created_at": "2026-03-26T15:30:12Z",
  "timestamp": 1774538412,
  "keywords": ["person"],
  "vlm_text": "A person is visible near the front door."
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | 파일명 (고유 식별자). 선두 8자리가 `YYYYMMDD` |
| `size` | int | 바이트 단위 파일 크기 |
| `created_at` | string (ISO 8601 UTC) | 파일 mtime |
| `timestamp` | int \| null | 메타 파일의 유닉스 타임스탬프. 없으면 mtime |
| `keywords` | string[] | 트리거된 키워드 목록 (메타 파일 기준) |
| `vlm_text` | string \| null | 이벤트 발생 시 VLM 응답 전문 |

> App 컨테이너(`:8080`)에도 `GET /clips`, `GET /clip/{name}`, `DELETE /clips`가 별도로 존재한다 (App 내부 디버깅/레거시용, 반환 스키마는 `:8000`과 유사하나 래퍼 `{clips, total}` 없이 배열만 반환). **프론트엔드는 `:8000`을 사용한다.**

### `GET /clips`

클립 목록 조회. 최신순 정렬.

이 엔드포인트가 클립 검색, 날짜 필터, 페이지네이션의 소스 오브 트루스입니다. 프론트엔드는 전체 목록을 받아 로컬에서 다시 자르지 않고, 현재 검색어/날짜 범위/페이지 크기/페이지 위치를 쿼리 파라미터로 전달하는 것을 기준으로 합니다.

**Query Parameters**:

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `q` | string | 선택 | `vlm_text` 필터 (부분 일치, 대소문자 무관) |
| `date_from` | string | 선택 | 시작 날짜 필터. `YYYY-MM-DD`, 로컬 날짜 기준, 해당 날짜 포함 |
| `date_to` | string | 선택 | 종료 날짜 필터. `YYYY-MM-DD`, 로컬 날짜 기준, 해당 날짜 포함 |
| `limit` | int | 선택 | 현재 페이지에 반환할 최대 개수. 페이지 크기 선택값은 `10`, `25`, `50`, `100`을 기준으로 사용 |
| `offset` | int | 선택 | 페이지네이션 오프셋. 기본값 0 (>=0) |

**Response `200`**:

```json
{
  "clips": [ /* ClipOut[] */ ],
  "total": 42
}
```

`total`은 필터 적용 후 전체 개수.

선택/삭제 UI는 현재 응답으로 표시된 페이지 범위만 대상으로 처리하는 것을 기준으로 합니다. 검색어, 날짜 필터, 페이지 크기, 페이지 위치가 바뀌면 이전 페이지 선택 상태는 유지하지 않습니다.

잘못된 날짜 형식(`date_from`, `date_to`)은 `400`으로 거절합니다.

### `GET /clips/{name}`

클립 파일 다운로드. Range 요청을 지원 — 브라우저 `<video>`가 자동으로 사용한다.

```html
<video src="http://<host>:8000/clips/20260326_153012_123.mp4?token=<JWT>" controls></video>
```

> `<video>` 태그는 `Authorization` 헤더를 설정할 수 없으므로, 위 예시처럼 `?token=` 쿼리를 사용합니다. API 서버의 `require_auth`는 Authorization 헤더와 쿼리 토큰 모두를 인식하므로 클립 다운로드에서도 쿼리 방식이 정상 동작합니다.

| 상태 코드 | 설명 |
|---|---|
| `200` | 전체 파일 (`Content-Type: video/mp4`) |
| `206` | 부분 콘텐츠 (Range 요청) |
| `400` | 잘못된 파일명 (경로 탈출) |
| `404` | 파일 없음 |
| `416` | 잘못된 Range 헤더 |

### `DELETE /clips`

선택 삭제. 파일명 배열로 지정한 클립과 짝이 되는 `.json` 메타 파일을 함께 삭제한다.

**Request Body**: `{ "names": ["20260326_153012_123.mp4", ...] }`

`names`가 빈 배열이면 아무것도 삭제하지 않는다.

**Response `200`**: `{"deleted": <int>}`

### `DELETE /clips/all`

`/data` 트리의 모든 mp4와 짝이 되는 `.json` 메타 파일을 전부 삭제한다.

**Response `200`**: `{"deleted": <int>}`

---

## 9. 이벤트 이력

> Base URL: `http://<host>:8000`

이벤트 이력은 SQLite `events` 테이블에 누적되는 별도 저장소입니다. **현재 App 컨테이너는 트리거 감지 시 클립 파일과 동명의 `.json` 메타데이터만 저장하며, `POST /events`를 자동 호출하지 않습니다.** 따라서 `GET /events`는 수동으로 `POST /events`를 호출한 기록만 반환하고, 자동 트리거 이력은 클립 목록(`GET /clips`)의 `keywords`/`vlm_text` 필드를 통해 조회해야 합니다. 자동 기록은 추후 구현 예정입니다.

### 데이터 모델

```json
{
  "id": 1,
  "trigger": "person detected",
  "clip_name": "20260326_153012_123.mp4",
  "created_at": "2026-03-26T15:30:12Z"
}
```

### `GET /events`

이벤트 이력 조회. 최신순 정렬.

| Query | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `limit` | int | 50 (>=1) | 최대 반환 개수 |
| `offset` | int | 0 (>=0) | 페이지네이션 오프셋 |

**Response `200`**: `{ "events": [...], "total": <int> }`

### `POST /events`

이벤트를 수동으로 기록합니다. 현재 App은 이 엔드포인트를 호출하지 않으므로, 외부 통합이나 테스트 목적으로만 사용합니다.

**Request Body**: `{ "trigger": "person detected", "clip_name": "..." }` (`clip_name`은 선택)

**Response `201`**: 생성된 `EventOut`.

### `DELETE /events`

이벤트 이력 전체 삭제.

**Response `200`**: `{"deleted": <int>}`

---

## 10. 기기 토큰

> Base URL: `http://<host>:8000`

Android 앱이 FCM 토큰을 등록·갱신하기 위한 CRUD 엔드포인트입니다. **현재 App 컨테이너에는 FCM 송신 구현이 없으므로, 여기에 등록된 토큰으로 실제 푸시가 전달되지는 않습니다.** `docker-compose.yml`의 `FCM_CREDENTIALS`/`FCM_TOKEN` 환경변수는 향후 송신 로직이 붙을 때를 위한 placeholder입니다.

### 데이터 모델

```json
{
  "id": 1,
  "fcm_token": "fGH3k...",
  "label": "my-phone",
  "registered_at": "2026-03-26T10:00:00Z"
}
```

### `GET /devices`

**Response `200`**: `{ "devices": [...] }`

### `POST /devices`

기기 토큰 등록 또는 갱신. `fcm_token`이 이미 존재하면 `label`만 갱신한다 (upsert).

**Request Body**: `{ "fcm_token": "...", "label": "my-phone" }` (`label` 선택)

**Response `200`**: 생성/갱신된 `DeviceOut`.

### `DELETE /devices/{id}`

**Response**: `200 {"deleted": 1}` / `404 {"detail": "device not found"}`

---

## 11. 헬스체크

### `GET http://<host>:8000/health` — API 서버
### `GET http://<host>:8080/` — App 서버

둘 다 인증 면제. **Response `200`**: `{"status": "ok"}`

---

## 12. 공통 사항

### 에러 응답

**API 서버(`:8000`)**: 모든 에러가 FastAPI 기본 포맷(`{"detail": "..."}`)을 따릅니다.

```json
{ "detail": "clip not found" }
```

**App 서버(`:8080`)**: 일부 경로(인증 실패의 `401`, `/prompt`/`/ptz`/`/vlm/switch`의 핸들러 내부 응답)는 JSON을 반환하지만, 경로 탈출·잘못된 파일명(`400`), 클립 누락(`404`), Range 오류(`416`), 미지원 메서드/경로(`404`) 등은 `BaseHTTPRequestHandler.send_error()`가 송출하는 기본 HTML 에러 페이지로 응답합니다. 클라이언트는 App 서버 응답에 대해 JSON 파싱에 실패할 수 있음을 전제로 해야 합니다.

| 상태 코드 | 의미 |
|---|---|
| `400` | 잘못된 요청 (경로 탈출, 유효성) |
| `401` | 인증 실패 또는 토큰 만료 |
| `404` | 리소스 없음 |
| `416` | 잘못된 Range 헤더 |
| `422` | 요청 바디 유효성 실패 (FastAPI 기본, API 서버만 해당) |
| `500` | 서버 내부 오류 |
| `502` | 상위 서비스 호출 실패 (주로 API→App 프록시) |

### 엔드포인트 전체 목록

| 서비스 | 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|---|
| MediaMTX :8888 | GET | `/live/index.m3u8` | × | HLS 라이브 스트림 |
| MediaMTX :8889 | — | `/live/whep` | × | WebRTC WHEP |
| App :8080 | GET | `/` | × | 헬스체크 |
| App :8080 | GET | `/stream` | ○ | MJPEG (VLM 입력 프레임) |
| App :8080 | GET | `/events` | ○ | SSE (시스템 상태) |
| App :8080 | POST | `/prompt` | ○ | VLM 프롬프트/트리거 변경 |
| App :8080 | POST | `/vlm/switch` | ○ | VLM 모델 전환 |
| App :8080 | POST | `/ptz` | ○ | PTZ 카메라 제어 |
| App :8080 | GET | `/camera` | ○ | 카메라 프로파일 (원본) |
| App :8080 | POST | `/camera` | ○ | 카메라 프로파일 적용 (원본) |
| App :8080 | GET | `/clips` | ○ | 클립 목록 (레거시/내부) |
| App :8080 | GET | `/clip/{name}` | ○ | 클립 파일 (레거시/내부) |
| App :8080 | DELETE | `/clips` | ○ | 클립 삭제 (레거시/내부) |
| API :8000 | POST | `/api/login` | × | 로그인 |
| API :8000 | POST | `/api/refresh` | × | 토큰 갱신 |
| API :8000 | POST | `/api/logout` | × | 로그아웃 (리프레시 토큰 폐기) |
| API :8000 | POST | `/api/change-password` | ○ | 비밀번호 변경 |
| API :8000 | GET | `/health` | × | 헬스체크 |
| API :8000 | GET | `/camera` | ○ | 카메라 프로파일 (프록시) |
| API :8000 | POST | `/camera` | ○ | 카메라 프로파일 적용 (프록시) |
| API :8000 | GET | `/clips` | ○ | 클립 목록 |
| API :8000 | GET | `/clips/{name}` | ○ | 클립 파일 다운로드 |
| API :8000 | DELETE | `/clips` | ○ | 클립 선택 삭제 |
| API :8000 | DELETE | `/clips/all` | ○ | 클립 전체 삭제 |
| API :8000 | GET | `/events` | ○ | 이벤트 이력 조회 |
| API :8000 | POST | `/events` | ○ | 이벤트 수동 기록 (외부 통합/테스트용) |
| API :8000 | DELETE | `/events` | ○ | 이벤트 이력 전체 삭제 |
| API :8000 | GET | `/devices` | ○ | 기기 목록 |
| API :8000 | POST | `/devices` | ○ | 기기 등록/갱신 |
| API :8000 | DELETE | `/devices/{id}` | ○ | 기기 삭제 |

### 컨테이너 구성

클립 저장소와 SQLite DB는 호스트의 `./data` 디렉토리 하나에 통합돼 있으며, App과 API 두 컨테이너가 같은 호스트 경로를 각자 `/data`로 바인드 마운트한다. JWT 시크릿은 두 컨테이너가 공유한다.

```yaml
app:
  environment:
    - JWT_SECRET=${JWT_SECRET:-babycat-default-secret}
    - VLM_MODELS=${VLM_MODELS:-Efficient-Large-Model/VILA1.5-3b}
    # - FCM_CREDENTIALS=/run/fcm/credentials.json
    # - FCM_TOKEN=<device_fcm_registration_token>
  volumes:
    - ./data/models:/data/models # NanoLLM model cache
    - ./data:/data           # 클립 저장 ({YYYY}/{MM}/*.mp4)
    - ./config:/config       # cam_profile.json
  ports:
    - "8080:8080"

api:
  environment:
    - CAM_DIR=/data
    - DB_PATH=/data/db/babycat.db
    - JWT_SECRET=${JWT_SECRET:-babycat-default-secret}
    - DEFAULT_USER=${DEFAULT_USER:-admin}
    - DEFAULT_PASS=${DEFAULT_PASS:-admin}
    # - CORS_EXTRA_ORIGINS=https://example.com
  volumes:
    - ./data:/data           # 클립 + SQLite (App과 동일 경로)
  ports:
    - "8000:8000"
  depends_on:
    - app

babycat-mediamtx:
  environment:
    - MTX_WEBRTCADDITIONALHOSTS=${HOST_IP:-}
  ports:
    - "8554:8554"      # RTSP
    - "8888:8888"      # HLS
    - "8889:8889"      # WebRTC HTTP
    - "8890:8890/udp"  # WebRTC ICE
```

> **클립 공유**: App과 API가 동일한 호스트 경로(`./data`)를 마운트한다. App은 ffmpeg로 `{YYYY}/{MM}/*.mp4`에 녹화하고, API는 같은 트리를 rglob하여 목록/다운로드/삭제를 제공한다.
> **`HOST_IP`**: MediaMTX 컨테이너는 호스트 NIC를 볼 수 없으므로 `.env`의 `HOST_IP`가 WebRTC ICE 후보로 광고된다. 설정 누락 시 외부에서 WebRTC 접속 불가.

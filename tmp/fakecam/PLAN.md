# fakecam 구현 계획

본 문서는 babycat의 VLM 인식 성능 및 파이프라인 호환성을 일관된 입력으로 검증하기 위한 보조 도구 `fakecam`의 설계와 구현 계획을 기술한다.

## 0. 목적과 위치

- babycat은 RTSP 카메라 영상만을 입력으로 인정한다. 이로 인해 동일한 영상을 동일한 조건으로 반복 주입하기 어렵고, VLM 인식 성능의 향상 여부를 객관적으로 비교하기 어렵다.
- `fakecam`은 babycat 입장에서 일반 IP 카메라와 동일한 RTSP 송출원으로 동작하면서, 내부적으로는 사용자가 지정한 mp4 파일들을 재생 목록 기반으로 매끄럽게 송출한다.
- babycat 본체와는 별도의 Compose 스택으로 동작하며, 본 프로젝트의 배포 빌드에는 포함되지 않는다.

## 1. 사용자 측 동작 사양 (확정)

### 1.1 카메라의 실재성

- RTSP만 호환. ONVIF 및 PTZ는 미지원.
- babycat의 카메라 프로파일에 IP·포트·아이디·암호·경로를 입력하여 접속.

### 1.2 영상 전환

- RTSP 세션을 유지한 채 내부 입력만 교체 (연속 전환).
- babycat의 GStreamer 파이프라인에서 caps 재협상이 발생하지 않도록, 모든 송출 영상이 동일한 해상도·프레임율·코덱·픽셀 포맷을 가짐.

### 1.3 웹 UI 배치

- babycat 본체(`web/`)와 분리된 독립 Compose 스택.
- 인증 없음.

### 1.4 레이아웃

```
[상단바]
[파일 트리] [재생 목록] [세부설정]
                       [하단 컨트롤]
```

### 1.5 파일 트리 패널

- 검색어 입력 필드 — 필터 방식 (일치하지 않는 항목 숨김, 일치 항목의 조상 디렉터리 자동 펼침). 검색 범위는 모든 mp4 파일.
- 체크박스 전체 선택/해제 토글 — 현재 보이는(필터링된) 항목에만 작용.
- 목록에 추가 버튼(+) — 체크된 항목 중 재생 목록에 없는 것만 추가. 트리의 체크 상태는 + 클릭 후에도 유지.
- mp4 파일에만 체크박스 존재. 디렉터리는 접기/펼치기 가능.
- 체크박스 영역의 클릭만이 체크 상태를 변경 (다중 선택·드래그 박스 등 도입 없음).

### 1.6 재생 목록 패널

- 검색어 입력 필드 — 필터 방식.
- 체크박스 전체 선택/해제 토글 — 현재 보이는 항목에만 작용.
- 목록에서 제거 버튼 (휴지통) — 체크된 항목을 일괄 제거.
- 정렬: 이름 순.
- 체크박스 영역의 클릭만이 체크 상태를 변경.
- 현재 재생 항목은 선택 강조와는 다른 시각 표시(예: 좌측 재생 아이콘 또는 별도 배경색)로 구분.

### 1.7 하단 컨트롤

| 버튼 | 동작 |
|---|---|
| 셔플 | 켜기 / 끄기 토글 |
| 이전 파일 | 직전 항목으로 이동 |
| 재생 / 정지 | 토글. 재생은 항상 재생 목록의 첫 항목부터 시작. 정지는 완전한 리셋. |
| 다음 파일 | 다음 항목으로 이동 |
| 반복 모드 | 전체 반복 / 단일 반복 / 끄기의 3단 토글 |

- 빈 재생 목록 상태에서 재생 버튼: 무동작.

### 1.8 재생 중 상호작용

| 요소 | 재생 중 |
|---|---|
| 파일 트리 체크박스 | 비활성화 |
| 재생 목록 체크박스 | 비활성화 |
| +, 휴지통, 전체 선택/해제 토글 | 비활성화 |
| 검색어 입력 | **활성** (사용 가능) |
| 하단 컨트롤 | 활성 (셔플 / 이전 / 정지 / 다음 / 반복 모드) |

### 1.9 세부설정 패널

```
[접속 정보]
- 아이디        : admin (편집 가능)
- 암호          : admin (편집 가능)
- 포트          : 554   (편집 가능)
- RTSP 경로     : /live (편집 가능)

[송출 사양]
- 해상도        : 360p / 720p / 1080p
- 프레임율      : 10 / 15 / 20 / 25 / 30 / 60
- 비트레이트    : 1 / 2 / 4 / 8 Mbps
- 오디오        : 제거 / 유지

[고정값 (UI 미노출)]
- 픽셀 포맷     : yuv420p
- 코덱          : H.264
- 키프레임 간격 : 1 s
```

비트레이트의 권장 기본값은 해상도에 따라 360p / 720p / 1080p에서 각각 1 / 2 / 4 Mbps이다. 키프레임 간격 1 s는 babycat의 세그먼트 레코더(`TRIGGER_SEGMENT_TIME=1s`)와 정합되도록 선택한 값이다.

## 2. 디렉터리 구조

```
fakecam/
├── PLAN.md                     # 본 문서
├── README.md                   # 사용 방법 요약 (Phase 4에 작성)
├── docker-compose.yml          # 두 컨테이너(server, web)를 함께 기동
├── videos/                     # 사용자가 mp4를 채워 넣는 디렉터리 (bind mount)
├── server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py             # 진입점 (GLib + uvicorn 통합)
│       ├── api.py              # FastAPI 라우터
│       ├── schemas.py          # Pydantic 모델
│       ├── library.py          # videos/ 스캔, 트리 구성
│       ├── playlist.py         # 재생 목록 상태와 조작
│       ├── playback.py         # 재생 상태 머신 (셔플·반복·이전·다음)
│       ├── settings.py         # 송출 설정 및 영속화
│       ├── pipeline.py         # GStreamer 파이프라인 빌더
│       └── rtsp_server.py      # gst-rtsp-server 래퍼
└── web/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js
        ├── App.vue
        ├── api.js              # 백엔드 호출 래퍼
        ├── composables/
        │   ├── useLibrary.js
        │   ├── usePlaylist.js
        │   ├── useSettings.js
        │   ├── usePlayback.js
        │   └── useEvents.js    # SSE 구독
        └── components/
            ├── TopBar.vue
            ├── FileTree.vue
            ├── Playlist.vue
            ├── SettingsPanel.vue
            └── BottomControls.vue
```

## 3. 기술 스택 및 의존성

### 3.1 server

| 항목 | 선택 | 비고 |
|---|---|---|
| 언어 | Python 3.11 | |
| HTTP 프레임워크 | FastAPI + uvicorn | 자동 OpenAPI 스펙, Pydantic 검증 |
| RTSP 서버 | `gst-rtsp-server` (Python 바인딩) | RTSP Basic 인증 내장 |
| 미디어 파이프라인 | GStreamer 1.x (`gi.repository`) | `concat` 엘리먼트로 매끄러운 전환 |
| 베이스 이미지 | `ubuntu:22.04` | GStreamer plugins, gst-rtsp-server를 apt로 설치 |

`requirements.txt`:

```
fastapi
uvicorn[standard]
pydantic
```

apt 패키지:

```
python3, python3-pip, python3-gi, python3-gst-1.0,
gir1.2-gst-rtsp-server-1.0,
gstreamer1.0-tools, gstreamer1.0-plugins-base,
gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad,
gstreamer1.0-plugins-ugly, gstreamer1.0-libav
```

### 3.2 web

| 항목 | 선택 | 비고 |
|---|---|---|
| 프레임워크 | Vue 3 + Vite | `babycat/web/`과 일관성 유지 |
| HTTP 클라이언트 | `fetch` + 경량 래퍼 | |
| 라우팅 | 없음 (단일 페이지) | |
| 인증 | 없음 | |
| 베이스 이미지 (배포) | `nginx:alpine` | Vite 빌드 결과를 정적 서빙 |

## 4. 시스템 동시성 구조

server 컨테이너 내부에는 다음 두 개의 이벤트 루프가 공존한다.

1. **GLib MainLoop** — GStreamer 파이프라인의 버스 메시지 처리 및 `gst-rtsp-server`의 클라이언트 세션 관리.
2. **asyncio Event Loop** — FastAPI/uvicorn의 HTTP 및 SSE 요청 처리.

두 루프 간의 결합:

- GLib MainLoop은 별도 데몬 스레드에서 실행한다.
- 메인 스레드는 uvicorn을 실행한다.
- HTTP 핸들러에서 파이프라인을 조작해야 할 때는 `GLib.idle_add`로 작업을 GLib 스레드에 위임한다.
- GStreamer 측에서 SSE 이벤트를 발행할 때는 `loop.call_soon_threadsafe`로 asyncio 큐에 push.

공유 상태는 `playback.PlaybackState` 단일 객체에 모아 두고, 스레드 락을 통해 보호한다.

## 5. 제어 API 스펙

모든 엔드포인트는 `/api/` 프리픽스를 가지며 JSON으로 응답한다.

### 5.1 라이브러리

```
GET /api/library
```

응답:

```json
{
  "tree": {
    "name": "videos",
    "type": "dir",
    "children": [
      {
        "name": "type_01",
        "type": "dir",
        "children": [
          { "name": "case_01.mp4", "type": "file", "path": "type_01/case_01.mp4", "size_bytes": 1234567 }
        ]
      },
      { "name": "etc_01.mp4", "type": "file", "path": "etc_01.mp4", "size_bytes": 9999 }
    ]
  }
}
```

디렉터리 우선 + 사전순 정렬. mp4 파일만 포함.

### 5.2 재생 목록

```
GET  /api/playlist
POST /api/playlist/add        body: { "paths": ["type_01/case_01.mp4", ...] }
POST /api/playlist/remove     body: { "paths": ["type_01/case_01.mp4", ...] }
```

`Playlist` 응답 형식:

```json
{
  "items": [
    { "path": "type_01/case_01.mp4", "name": "case_01.mp4" }
  ],
  "current_path": "type_01/case_01.mp4",
  "is_playing": true
}
```

- `add`는 중복을 무시한다.
- `remove`는 존재하지 않는 항목을 무시한다.
- 재생 중 `add` / `remove`는 `409 Conflict`로 거부한다 (UI 결정과 일치하나 백엔드 안전망 차원).

### 5.3 재생 제어

```
POST /api/playback/play
POST /api/playback/stop
POST /api/playback/next
POST /api/playback/prev
PUT  /api/playback/mode       body: { "shuffle": true, "repeat": "all" }
```

`repeat`: `"off" | "all" | "one"`.

모든 응답은 `Playlist` 객체 + `mode` 필드.

### 5.4 설정

```
GET /api/settings
PUT /api/settings             body: Partial<Settings>
```

`Settings`:

```json
{
  "auth_user": "admin",
  "auth_password": "admin",
  "port": 554,
  "rtsp_path": "/live",
  "resolution": "720p",
  "fps": 30,
  "bitrate_mbps": 2,
  "audio": "drop"
}
```

- 설정 변경은 즉시 디스크에 영속화된다.
- 포트 변경 또는 인증 변경은 RTSP 서버 재시작을 요구하므로 재생 중이라면 `409`로 거부.
- 해상도·FPS·비트레이트·오디오 변경은 재생 중이 아닐 때만 다음 재생부터 적용. 재생 중에는 동일하게 `409`.

### 5.5 라이브 이벤트 (SSE)

```
GET /api/events
```

서버 → 클라이언트 푸시:

```
data: {"type": "playlist", "playlist": {...}}
data: {"type": "playback", "current_path": "...", "is_playing": true}
data: {"type": "settings", "settings": {...}}
data: {"type": "error", "message": "..."}
```

신규 구독자에게는 초기 스냅샷을 즉시 전송한다.

## 6. RTSP 파이프라인 설계

### 6.1 송출 파이프라인 (단일 영상 기준)

```
filesrc location={path}
  ! qtdemux name=demux
  demux.video_0 ! h264parse ! avdec_h264
  ! videoscale ! video/x-raw,width={W},height={H}
  ! videorate ! video/x-raw,framerate={F}/1
  ! videoconvert ! video/x-raw,format=I420
  ! x264enc bitrate={B*1000} key-int-max={F} speed-preset=veryfast tune=zerolatency
  ! rtph264pay name=pay0 pt=96
```

오디오 유지 옵션 선택 시 `demux.audio_0`을 `aacparse ! rtpmp4apay name=pay1 pt=97`로 분기.

### 6.2 영상 전환 방식

`gst-rtsp-server`의 `GstRTSPMediaFactory`를 상속하여 `create_element` 메서드에서 위 파이프라인의 최상위에 `concat` 엘리먼트를 배치한다. 영상 전환 절차:

1. 다음 영상을 위한 디코딩 체인을 미리 준비.
2. `concat`의 `current` 패드가 EOS에 도달하면 자동으로 다음 입력으로 전환.
3. 사용자가 명시적으로 다음/이전/점프를 요청한 경우, 현재 입력을 강제 EOS시켜 전환을 유발.

이 방식은 RTSP 세션과 caps를 유지한 채 영상만 매끄럽게 교체한다.

### 6.3 인증

`gst-rtsp-server`의 `GstRTSPAuth`를 사용하여 Basic 인증을 적용한다. 설정의 `auth_user` / `auth_password`가 변경되면 `GstRTSPAuth`의 토큰을 재발급한다.

## 7. Docker 구성

### 7.1 `docker-compose.yml` (예상)

```yaml
services:
  fakecam-server:
    build: ./server
    container_name: fakecam-server
    network_mode: host
    volumes:
      - ./videos:/videos:ro
      - ./server/state.json:/state.json
    environment:
      - VIDEOS_DIR=/videos
      - STATE_PATH=/state.json
      - API_PORT=8090
    restart: unless-stopped

  fakecam-web:
    build: ./web
    container_name: fakecam-web
    ports:
      - "5174:80"
    depends_on:
      - fakecam-server
    restart: unless-stopped
```

- `network_mode: host`를 사용하는 이유는 RTSP 클라이언트가 표준 포트 554에 접근하고 RTSP의 동적 포트 핸들링과 충돌하지 않도록 하기 위함이다.
- 웹 UI는 5174 포트에 노출한다 (babycat web의 5173과 구분).
- 사용자는 babycat의 카메라 프로파일에 `host_ip:554`, `admin`, `admin`을 입력하여 fakecam을 연결한다.

### 7.2 `server/Dockerfile` (예상)

```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-gi python3-gst-1.0 \
    gir1.2-gst-rtsp-server-1.0 \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY src/ ./src/
CMD ["python3", "-m", "src.main"]
```

### 7.3 `web/Dockerfile`

`babycat/web/Dockerfile`을 참고하여 Vite 빌드 결과를 nginx 정적 서빙. 개발 단계에서는 `vite dev`를 직접 컨테이너로 띄우는 별도 변형도 둔다.

## 8. 작업 순서

각 Phase는 종료 시점에 동작 가능한 산출물을 가지도록 구성한다.

### Phase 1 — 서버 골격 및 단일 영상 송출

1. `server/` 디렉터리 골격 및 `Dockerfile`, `requirements.txt`.
2. `library.py` — `videos/` 디렉터리 스캔, 트리 직렬화.
3. `settings.py` — 설정의 디스크 영속화.
4. `pipeline.py` — 단일 mp4를 받아 RTSP 송출하는 GStreamer 파이프라인.
5. `rtsp_server.py` — `gst-rtsp-server` 래퍼, 인증 적용.
6. `main.py` — GLib MainLoop과 uvicorn 통합.
7. `api.py` — `GET /library`, `GET /settings`, `PUT /settings`만 우선 노출.
8. **검증**: `vlc rtsp://admin:admin@host:554/live`로 단일 영상이 정상 송출됨을 확인.

### Phase 2 — 재생 목록 및 매끄러운 전환

9. `playlist.py` — 재생 목록 상태와 조작.
10. `playback.py` — 셔플·반복·이전·다음 로직.
11. `pipeline.py` — `concat` 기반 매끄러운 전환 구현.
12. `api.py` — 재생 목록 및 재생 제어 엔드포인트 추가.
13. `api.py` — SSE 이벤트 채널.
14. **검증**: `curl`로 재생 목록을 조작하면서 VLC 상에서 영상이 매끄럽게 전환됨을 확인.

### Phase 3 — 웹 UI

15. `web/` 골격 (Vite + Vue 3).
16. `api.js`와 composable들.
17. 최상위 3분할 레이아웃 (`App.vue`).
18. `FileTree.vue` — 트리, 검색, 체크박스, + 버튼.
19. `Playlist.vue` — 리스트, 검색, 체크박스, 휴지통, 현재 재생 항목 표시.
20. `SettingsPanel.vue`.
21. `BottomControls.vue` — 5종 컨트롤.
22. SSE 구독으로 라이브 갱신 연결.
23. **검증**: 브라우저에서 모든 사양 항목이 의도대로 동작함을 수동 확인.

### Phase 4 — babycat 연동 검증

24. babycat 본 스택과 fakecam을 동일 호스트에서 함께 기동.
25. babycat의 카메라 프로파일에 fakecam의 RTSP 자격증명을 입력.
26. fakecam에서 재생 → babycat에서 영상이 수신되고 VLM이 동작함을 확인.
27. 영상 전환 시 babycat의 워치독이 재시작을 유발하지 않음을 확인 (만약 유발한다면 6.2의 전환 방식 재검토).
28. `fakecam/README.md` 작성.

## 9. 위험 요소와 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| `concat` 기반 전환 시 caps 재협상으로 RTSP 클라이언트 disconnect | 매끄러운 전환 실패 | 입력 영상을 사전에 동일 caps로 정규화하는 인코딩 단을 두고, `concat`은 인코딩 후 단계에 배치하지 않도록 설계 |
| `gst-rtsp-server` Python 바인딩 문서 부족 | 구현 지연 | 공식 예제(`test-launch.py`, `test-auth.py`)와 GStreamer 메일링 리스트의 사례 참조. Phase 1에서 인증을 먼저 검증 |
| Jetson과 일반 PC 간 GStreamer 플러그인 차이 | 환경 의존성 | `x264enc` 등 일반 플러그인만 사용. `nvv4l2*`는 사용하지 않음 |
| 호스트 네트워크 모드의 부작용 | macOS·Windows에서 동작하지 않음 | 본 도구는 Linux 환경(특히 babycat이 동작하는 환경)을 전제로 함을 README에 명시 |
| RTSP 554 포트의 권한 문제 | 컨테이너가 1024 미만 포트에 바인드 실패 | `network_mode: host` 사용 시 컨테이너 안에서 root로 실행되면 가능. 또는 8554로 변경 가능하도록 설정 UI에서 입력을 허용 |

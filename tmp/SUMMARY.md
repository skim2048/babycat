# babycat — 코드 기반 아키텍처 요약

본 문서는 `./web`, `./fakecam`을 제외한 babycat 본체 코드를 직접 읽고 정리한 내용과, `./web`을 포함한 외부 카메라 → 이벤트 클립 저장까지의 전체 흐름을 함께 담는다. 어떤 README/요약 문서도 참조하지 않고 소스만 보고 작성하였다.

---

## 1. 한 문장 요약

**RTSP 카메라 영상을 MediaMTX로 받아 Jetson Orin NX에서 GStreamer로 디코딩하고, 일정 간격으로 추출한 프레임을 VLM(NanoLLM/MLC)에 넣어 "사람이 무엇을 하는지"를 추론한 뒤, 사용자가 지정한 트리거 키워드가 매칭되면 그 순간 전후의 영상을 클립으로 저장하는 시스템.**

---

## 2. 컨테이너 토폴로지 ([docker-compose.yml](docker-compose.yml))

| 서비스 | 역할 | 외부 포트 |
|---|---|---|
| `mtx` | MediaMTX. RTSP/HLS/WebRTC 미디어 서버. App이 런타임에 API로 source를 주입 | 8554/8888/8889/8890 |
| `app` | GStreamer + VLM 추론 + 자체 HTTP 서버(8080). NVIDIA 런타임, Orin의 nvdec/nvenc/nvmap 디바이스 접근 | 8080 |
| `api` | FastAPI 게이트웨이. 인증/클립 목록/이벤트/디바이스 관리, 카메라 설정은 `app`으로 프록시 | 8000 |

데이터는 모두 `./data` 볼륨 공유. App은 추가로 `tmpfs:/run/babycat-segments`를 가져 rollover 세그먼트를 메모리에 보관한다.

---

## 3. 두 개의 평면 — 외부 평면(api)과 내부 평면(app)

이 분리가 babycat 설계의 핵심 골격이다.

**외부 평면 — [api/main.py](api/main.py)**
- FastAPI 기반, 클라이언트가 보는 단일 진입점
- 자체 책임: 인증/세션, 클립 파일 시스템 조회, 이벤트/디바이스 SQLite 관리
- 위임 책임: `/camera` GET/POST → [api/app_proxy.py](api/app_proxy.py)를 통해 `http://app:8080`으로 HTTP 프록시
- 인증은 자체 구현 JWT(HMAC-SHA256, [api/auth.py](api/auth.py)), PBKDF2 패스워드, in-memory 로그인 시도 제한(10회/30분 락아웃), refresh token 회전(DB에 해시만 저장)

**내부 평면 — [app/server.py](app/server.py)**
- `BaseHTTPRequestHandler` 기반 자체 HTTP 서버(FastAPI 아님)
- 같은 JWT 시크릿을 공유하여 토큰 검증([app/server_support.py:17](app/server_support.py#L17))
- MJPEG 스트림, SSE(상태 푸시), 클립 다운로드(Range 지원), `/prompt`, `/ptz`, `/camera`, `/vlm/switch`, `/clips DELETE`

같은 클립 파일을 두 평면이 모두 다룬다. 경로 해석 로직이 두 곳에 거의 동일하게 존재한다 — [api/clip_support.py:19](api/clip_support.py#L19)와 [app/server_support.py:39](app/server_support.py#L39). 두 평면이 같은 볼륨을 보는 단일 카메라 가정의 결과다.

---

## 4. 미디어 파이프라인 ([app/main.py](app/main.py))

```
RTSP 카메라 → mtx(MediaMTX) → rtspsrc → rtph264depay → h264parse
            → nvv4l2decoder(HW) → nvvidconv(RGBA)
            → videorate(TARGET_FPS=1.0) → appsink
            → RingBuffer(30) → inference_worker(N_FRAMES=4) → VLM
            → 키워드 매칭 → save_trigger_clip
```

- MediaMTX는 카메라 자격증명을 모른다. App이 [camera.py:240](app/camera.py#L240)에서 MediaMTX HTTP API(`/v3/config/paths/patch/live`)에 RTSP URL을 PATCH하여 런타임에 source를 주입한다.
- App은 자신이 MediaMTX의 RTSP 출력을 다시 소비한다(`MEDIAMTX_URL = rtsp://mtx:8554/live`). 카메라를 직접 보지 않는 이유는 (a) 브라우저용 WebRTC/HLS와 App의 추론이 같은 한 번의 RTSP 풀(pull)을 공유하고, (b) 카메라 자격증명이 클라이언트로 새지 않게 하기 위함이다.
- `videorate`로 1 FPS로 정규화. 1초마다 한 장이 RingBuffer에 들어가고, 가장 최근 4프레임이 VLM에 들어간다.

---

## 5. VLM 자식 프로세스 격리 ([app/vlm_worker.py](app/vlm_worker.py))

설계상 가장 신경 쓴 결정으로 보이는 부분.

NanoLLM/MLC/TensorRT가 모델 교체 시 CUDA/TVM 네이티브 메모리를 안정적으로 풀어주지 않는다. Orin은 GPU/CPU 메모리가 하나의 풀이라 누수가 RAM 점유로 직결된다. 그래서 **VLM을 부모와 분리된 자식 프로세스에서 실행**한다.

- 부모: GStreamer, RingBuffer, HTTP 서버 (CUDA 미접촉)
- 자식: `python3 vlm_worker.py <model_id> <ipc_addr>` (AF_UNIX, multiprocessing.connection, authkey 인증)
- 모델 전환 = 자식 종료 → 새 자식 spawn (OS가 메모리 회수)
- 같은 이유로 부팅 시 사전컴파일도 서브프로세스로 순차 수행([app/main.py:665](app/main.py#L665) `_precompile_one`)

`holder.py`는 의도적인 별도 모듈이다. `python main.py`로 실행되면 `main`이 `__main__`으로 로드되는데, `server.py`에서 `from main import ...`을 하면 `main`이 또 다른 모듈로 이중 로드되어 전역이 분열된다. 그 함정을 피하려고 VLM 홀더 싱글톤만 [app/holder.py](app/holder.py)로 빼두었다.

---

## 6. 트리거 클립 — 두 가지 모드

키워드 매칭이 발생하면 [app/main.py:568](app/main.py#L568) `save_trigger_clip`이 호출된다. 두 가지 경로가 있다.

**A. Direct mode (기본)** — [app/main.py:327](app/main.py#L327)
- 이벤트 발생 시점부터 `ffmpeg -i rtsp://mtx/live -t 5 -c copy` 실행
- 단순하지만 "이벤트 이전 N초"는 잡지 못한다.

**B. Rollover mode** (`TRIGGER_ROLLOVER_ENABLED=1`, docker-compose에서 활성화) — [app/main.py:144](app/main.py#L144)
- 백그라운드 ffmpeg가 RTSP를 1초 단위 `.ts` 세그먼트로 tmpfs(`/run/babycat-segments/live`)에 항상 기록 (15초 보존)
- 이벤트 발생 시 `[event-2초, event+5초]` 윈도우에 걸친 세그먼트들을 concat manifest로 묶어 `ffmpeg -f concat -c copy`로 한 mp4로 결합
- 즉, **사후 인지 시 사전 영상까지 잡아낸다**.
- 실패하면 Direct 모드로 자동 폴백

저장 형식은 두 모드 동일: `{DATA_DIR}/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4` + 같은 이름의 `.json` 메타파일(이벤트 시각, 매칭 키워드, VLM 텍스트, 진단용 타이밍 정보).

---

## 7. 상태 머신 ([app/state.py](app/state.py))

`AppState` 싱글톤이 모든 런타임 상태를 집약하고, SSE로 클라이언트에 푸시한다.

- **Pipeline 상태**: `idle | starting | restarting | streaming | stalled | stopped`
  - 상세: `waiting_for_vlm`, `waiting_for_camera`, `watchdog_timeout`, `camera_apply` 등
- **VLM 상태**: `initializing → downloading → compiling → loading → ready → switching → error`
- **Segment recorder 상태**: `disabled | starting | running | error`
- **Clip storage 상태**: `ok | skipped | error` (디스크 부족 등)

상태 전이는 `mark_pipeline_*`, `set_vlm_state` 등 명시적 메서드로만 일어나고, 매번 `_sse_push()`로 SSE 구독자에게 즉시 전달된다.

---

## 8. 부팅 시퀀스 ([app/main.py:977](app/main.py#L977))

순서 자체가 설계 의도를 보여준다.

1. **HTTP 서버를 가장 먼저 띄움** (`start_server(8080)`) — VLM 로딩이 수십 분 걸릴 수 있으므로, 그 사이에도 사용자가 웹에서 카메라 자격증명을 입력할 수 있게 함
2. 백그라운드에서 저장된 카메라 프로필이 있으면 MediaMTX에 적용 (10회 백오프 재시도)
3. VLM 사전컴파일 (캐시 미스인 모델만, 서브프로세스로 순차)
4. 기본 모델 로드 (자식 프로세스)
5. RingBuffer / inference 큐 / 워커 스레드 / 워치독 스레드 기동
6. 카메라 ready면 즉시 파이프라인 PLAYING, 아니면 카메라 ready 시점까지 대기

---

## 9. PTZ ([app/ptz.py](app/ptz.py))

ONVIF SOAP을 외부 라이브러리 없이 직접 구현한다 (WS-Security UsernameToken, ContinuousMove/Stop/AbsoluteMove/GetStatus). 2초 주기 폴링으로 현재 좌표를 캐싱. "Home" 좌표는 카메라 프로필의 `ptz_home` 필드에 저장된다. 또한 PTZ가 움직이는 동안에는 inference_worker가 추론을 건너뛴다([app/main.py:783](app/main.py#L783)) — 움직이는 영상은 VLM에 의미가 없기 때문으로 보인다.

---

## 10. 워치독과 lifecycle policy

- [app/main.py:946](app/main.py#L946) `watchdog_worker`가 5초마다 검사: PLAYING 진입 후 15초 grace 이후에도 마지막 프레임 도착이 15초를 넘으면 파이프라인 재시작
- [app/pipeline_lifecycle.py](app/pipeline_lifecycle.py)는 "언제 시작/재시작이 가능한가"의 정책만 분리해서 들고 있는 작은 정책 객체. GStreamer 구체 호출은 main에 두고 가드만 객체화한 형태다.

---

## 11. 외부 평면이 자체 책임으로 유지하는 것 (api 컨테이너 단독)

- 사용자/세션 (users, refresh_tokens 테이블 — [api/auth.py](api/auth.py))
- 이벤트 로그 (events 테이블 — DB의 영구 기록은 api에만 존재)
- FCM 디바이스 등록 (devices 테이블)
- 클립 파일시스템 직접 조회/삭제 (같은 볼륨 마운트)

App은 SQLite를 쓰지 않는다. App의 "현재 상태"는 전부 in-memory(AppState) + 파일(클립 mp4 + .json + cam_profile.json). 영속화가 필요한 영역은 api 쪽으로 모았다고 읽힌다.

---

## 12. 코드만 보고 받은 인상

1. **두 평면 분리의 동기는 명확하다** — 외부 클라이언트 인증/REST 표준은 FastAPI 쪽에 두고, 내부 평면은 GStreamer 메인루프와 같은 프로세스에 가벼운 stdlib HTTP 서버를 둠. 두 평면이 같은 JWT 시크릿을 공유하여 자격증명은 외부 평면에서 발급되고 내부 평면은 검증만 한다.

2. **VLM 자식 프로세스 격리는 "성능 최적화"가 아니라 "메모리 누수에 대한 회피 설계"**다. holder 모듈의 존재, 서브프로세스 사전컴파일, switch 시 종료-spawn — 모두 같은 제약에서 파생된 일관된 선택이다.

3. **트리거 클립의 rollover 모드가 진짜 설계 의도**이고 direct 모드는 폴백이다. tmpfs 마운트, segment recorder 백그라운드 ffmpeg, watchdog까지 갖춰져 있어 "사후 인지로 사전 영상 회수"가 일급 시나리오로 보인다.

4. **`source_type` 추상화가 [camera.py](app/camera.py)에 있지만 실제 구현체는 `rtsp_camera` 단 하나**다 — `_source_normalizer`, `_source_profile_viewer`, `_source_runtime_activator`가 모두 단일 분기. 미래 확장의 자리는 비워뒀지만 지금은 한 종류뿐이다.

5. **클립 경로 해석 로직이 api 평면과 app 평면 양쪽에 거의 동일하게 존재**한다 ([api/clip_support.py:19](api/clip_support.py#L19) vs [app/server_support.py:39](app/server_support.py#L39)). 두 평면이 의도적으로 코드를 공유하지 않는(별도 컨테이너) 설계의 비용이다.

---

# 외부 카메라 → 이벤트 클립 저장까지 — 전체 시퀀스 (`./web` 포함)

등장 객체를 먼저 정리한다.

| | 위치 | 역할 |
|---|---|---|
| **Browser** | 클라이언트 | Vue 앱 (`./web`) |
| **api** | 컨테이너 :8000 | FastAPI. 인증·클립조회·`/camera` 프록시 |
| **app** | 컨테이너 :8080 | GStreamer + 추론 + 자체 HTTP 서버 |
| **vlm_child** | app 내부 자식 프로세스 | NanoLLM(VLM) 실행자 |
| **mtx** | 컨테이너 :8554/:8888/:8889 | MediaMTX. RTSP/HLS/WebRTC |
| **Camera** | 외부 RTSP 카메라 | 실 영상 소스 |

---

## Phase 0. 부팅 (사용자 개입 이전)

1. **app** 컨테이너가 [main.py:977](app/main.py#L977) `main()` 진입.
2. **app**이 `start_server(8080)`을 먼저 호출해 HTTP 서버를 띄움 — VLM 로딩 전부터 웹이 접속 가능하도록.
3. **app**이 `camera.startup_apply()`를 백그라운드 스레드로 띄움 — 저장된 `cam_profile.json`이 있으면 **mtx**에 RTSP source를 주입(없으면 그냥 통과).
4. **app**이 VLM 사전컴파일 → 기본 모델을 **vlm_child**(자식 프로세스)로 로드. 이 사이 SSE 상태는 `initializing → downloading → compiling → loading → ready`로 흐름.
5. 카메라가 ready면 GStreamer 파이프라인을 즉시 PLAYING. 아니면 `waiting_for_camera` 상태로 대기.

이 시점에서 **app**은 사용자 입력만 기다리는 상태다.

---

## Phase 1. 로그인

```
Browser ──POST /api/login──▶ api
        ◀── { token, refresh_token, expires_in } ──
```

- [useAuth.js:316](web/src/composables/useAuth.js#L316) `login()`이 호출.
- **api**는 [auth.py:197](api/auth.py#L197) `authenticate()`로 PBKDF2 검증, 락아웃 체크(10회/30분), 통과 시 JWT(HMAC-SHA256) + refresh token 발급.
- Browser는 `remember_me`에 따라 `localStorage`(영속) 또는 `sessionStorage`(임시)에 저장. 만료 1분 전 자동 refresh 타이머가 걸림.
- 이후 모든 API/App 요청은 `Authorization: Bearer <token>` 또는 `?token=...` 쿼리(EventSource·`<video>`처럼 헤더 못 다는 클라이언트용)로 동일한 JWT를 양 평면이 검증.

---

## Phase 2. 카메라 자격증명 입력

이 단계가 babycat 시스템에 "실제 카메라"가 처음 알려지는 지점이다.

```
Browser(CameraPanel)
   └─POST /camera ──▶ api ──proxy_app──▶ app:/camera ──┐
                                                        │
                              app.camera.apply()        │
                                  ├─ _normalize_profile (유효성)
                                  ├─ camera_ready.clear()
                                  ├─ _update_mediamtx() ── PATCH ──▶ mtx:9997/v3/config/paths/patch/live
                                  │                                  (source = rtsp://user:pw@cam_ip/stream1)
                                  ├─ camera_ready.set()
                                  ├─ save() → /config/cam_profile.json
                                  └─◀ { ok: true }
                                                        │
   ◀────────────── { ok: true } ────────────────────────┘

   app HTTP 핸들러는 응답 직후 별도 스레드로:
        threading.Thread(restart_pipeline, args=("camera_apply",))
```

- [useCamera.js:74](web/src/composables/useCamera.js#L74) `save()` → [api/main.py:194](api/main.py#L194) `set_camera()` → [api/app_proxy.py:17](api/app_proxy.py#L17) `proxy_app()` → [app/server.py:374](app/server.py#L374) `_handle_camera()` → [app/camera.py:60](app/camera.py#L60) `apply()`.
- **mtx**는 이제 PATCH로 받은 RTSP URL을 source로 **Camera**에 RTSP PULL 연결을 시작. 사용자 자격증명은 **mtx**와 **app**에만 존재(웹/브라우저까지 흘러가지 않음).
- [app/server.py:367](app/server.py#L367)에서 응답이 나간 뒤 **별도 스레드로** 파이프라인 재시작이 예약된다. 동기적으로 기다리지 않는 이유는 GStreamer 재시작이 수 초 걸릴 수 있어서.
- Browser 쪽은 `reconnectKey`를 bump해 LiveStream 컴포넌트가 HLS/WebRTC 연결을 재수립하도록 트리거.

---

## Phase 3. 라이브 스트림 — 세 갈래 동시 흐름

이 시점부터 **세 개의 독립적인 스트림**이 평행으로 흐른다.

```
Camera ─RTSP─▶ mtx ┬─RTSP /live──▶ app/GStreamer 파이프라인   (추론용, 1fps)
                   │
                   ├─RTSP /live──▶ app/segment_recorder ffmpeg (15초 롤링 .ts → tmpfs)
                   │
                   ├─HLS  :8888──▶ Browser/<video> via hls.js  (라이브 뷰)
                   ├─WHEP :8889──▶ Browser/<video> via WebRTC  (라이브 뷰, 저지연)

app/HTTP :8080 ─SSE /events─▶ Browser  (상태/추론결과 푸시)
app/HTTP :8080 ─MJPEG /stream─▶ Browser  (VLM 입력 프레임, 디버그용)
```

세 갈래의 책임 분리:

1. **추론 갈래** ([main.py:917](app/main.py#L917) `start_pipeline`): `rtspsrc → rtph264depay → h264parse → nvv4l2decoder(HW) → nvvidconv RGBA → videorate 1fps → appsink`. appsink 콜백이 매 프레임을 384×384 PIL로 변환해 [main.py:96](app/main.py#L96) `RingBuffer`에 push, `infer_queue`에 시그널.

2. **세그먼트 갈래** ([main.py:466](app/main.py#L466) `_segment_recorder_worker`): 별도 ffmpeg 프로세스가 mtx로부터 RTSP를 받아 1초 단위 `.ts` 세그먼트를 `/run/babycat-segments/live/`(tmpfs)에 계속 기록. 15초 지난 세그먼트는 자동 삭제.

3. **표시 갈래**: Browser는 [LiveStream.vue:10](web/src/components/LiveStream.vue#L10)에서 mtx의 HLS(`:8888/live/index.m3u8`) 또는 WebRTC WHEP(`:8889/live/whep`)에 직접 연결. **app은 이 경로에 관여하지 않는다** — 라이브 뷰는 mtx ↔ Browser 직통.

이와 별개로 Browser는 [useSSE.js:122](web/src/composables/useSSE.js#L122)에서 `app:8080/events?token=...`에 EventSource로 붙어 1초 미만 주기로 상태 스냅샷(VLM 상태, 파이프라인 상태, 하드웨어, PTZ, clip_count 등)을 받는다.

---

## Phase 4. 프롬프트·트리거 키워드 설정

사용자가 PromptPanel에서 "What is the person doing?" 같은 프롬프트와 "fall, fight" 같은 키워드 목록을 입력하면

```
Browser ──POST /prompt {prompt, triggers}──▶ app  ([app/server.py:302])
                                              └─ app_state.set_prompt(...)
                                                 app_state.set_triggers([...])
```

키워드는 소문자 정규화 후 리스트로 보관된다([server.py:309](app/server.py#L309)).

---

## Phase 5. 추론 루프 (1초당 1회)

```
GStreamer 콜백 스레드                inference_worker 스레드             vlm_child 프로세스
─────────────────────                ──────────────────────              ──────────────────
on_new_sample()
  ├─ ring.push(frame, captured_at)
  ├─ app_state.update_frame(...)
  │   └─ SSE push (frame_w/h 갱신)
  └─ infer_queue.put_nowait(True)
                                     infer_queue.get(timeout=5)
                                     pop_request() → 모델 전환 요청 있나?
                                       (있으면 vlm_proc.switch())
                                     ptz_is_moving()? → 움직이는 동안 skip
                                     samples = ring.latest_samples(N_FRAMES=4)
                                     vlm_proc.infer(frames, prompt) ──IPC──▶ chat = ChatHistory()
                                                                              for f in frames:
                                                                                chat.append('user', image=f)
                                                                              chat.append('user', text=prompt)
                                                                              tokens = model.generate(...)
                                                                ◀──IPC── return raw_text
                                     raw_lower = raw.lower()
                                     matched = [kw for kw in triggers if kw in raw_lower]
                                     app_state.update_inference(label, raw, ms, event_triggered=bool(matched))
                                       └─ SSE push (infer_raw + event_triggered 갱신)

                                     if matched:
                                       threading.Thread(save_trigger_clip, ...).start()
```

핵심 보호 장치:

- **PTZ 중에는 건너뜀** ([main.py:783](app/main.py#L783)): 움직이는 영상은 VLM에 의미가 없다.
- **모델 전환은 추론 사이에만** ([main.py:773](app/main.py#L773)): 생성 도중 전환이 발생할 수 없도록 holder.pop_request()를 루프 시작 지점에서만 호출.
- **VLM이 죽으면 자동 재spawn** ([vlm_worker.py:227](app/vlm_worker.py#L227)): 다음 infer() 호출 시 부모가 자식의 사망을 감지하고 같은 모델로 새 자식을 띄움.

---

## Phase 6. 이벤트 클립 저장 (Rollover 모드, 기본 설정)

`matched`가 있으면 [main.py:568](app/main.py#L568) `save_trigger_clip`이 데몬 스레드로 실행된다.

```
save_trigger_clip(matched, raw, event_time, ...)
  ├─ 쿨다운 검사 (TRIGGER_COOLDOWN=30s): 30초 내 또 매칭되면 무시
  ├─ clip_dir = app_state.get_clip_dir()  → /data
  │
  └─ _finalize_rollover_clip:
       ├─ window_start = event_time - 2s  (TRIGGER_PRE_EVENT_SEC)
       ├─ window_end   = event_time + 5s  (TRIGGER_POST_EVENT_SEC)
       │
       ├─ sleep(window_end - now)   ◀── 세그먼트가 채워질 때까지 대기 (보통 5초)
       │
       ├─ dest_dir = /data/{YYYY}/{MM}/   (mkdir -p)
       │
       ├─ ensure_clip_capacity():
       │     디스크 free가 CLIP_MIN_FREE_MB(256MB) 미만이면 오래된 클립부터 prune
       │
       ├─ select_segments_for_window(/run/babycat-segments/live, ws, we):
       │     [event-2초, event+5초] 윈도우와 겹치는 .ts 세그먼트들을 시간순으로 수집
       │
       ├─ write_concat_manifest(segments → <base>.segments.txt)
       │
       ├─ ffmpeg -f concat -safe 0 -i <manifest> -c copy /data/YYYY/MM/{base}.mp4
       │     ◀── 재인코딩 없이 단순 concat. 빠르고 CPU 부하 없음
       │
       ├─ probe_clip_duration_seconds(out_path)  ── ffprobe로 실측 길이 확인
       │
       ├─ {base}.json 사이드카 작성:
       │     { timestamp, event_time_ms, keywords, vlm_text,
       │       record_requested_at_ms, ffmpeg_started_at_ms,
       │       start_delay_ms, ffmpeg_elapsed_ms,
       │       clip_size_bytes, clip_duration_s,
       │       frame_time_ms, frame_to_event_ms,
       │       inference_started_at_ms, inference_elapsed_ms,
       │       record_mode: "segment_rollover",
       │       selected_segment_count, segment_window_start_ms, segment_window_end_ms }
       │
       ├─ app_state.invalidate_clip_cache()
       └─ app_state.set_clip_storage_status("ok", ..., free_mb)
              └─ SSE push (clip_count 갱신)
```

실패 시(이전 mediamtx가 멈춰 세그먼트가 비었거나 ffmpeg가 에러) **자동으로 Direct 모드로 폴백** — `ffmpeg -i rtsp://mtx/live -t 5 -c copy`로 사후 5초만 잡는 단순 경로 ([main.py:608](app/main.py#L608)).

저장 결과: `/data/2026/05/20260530_HHMMSS_mmm.mp4` + 같은 이름의 `.json`.

---

## Phase 7. 웹이 새 클립을 인지

```
app_state.set_clip_storage_status()  → SSE push  → Browser EventSource onmessage
                                                      └─ state.clip_count 갱신

Browser useClips.ensureWatcher():
  watch(sseState.clip_count) → clipVersion++

ClipsPanel:
  watch(clipVersion) → authFetch(API_ENDPOINTS.clips)
                          ──GET /clips──▶ api
                                            └─ _list_clips() rglob /data/**/*.mp4
                                               + 사이드카 .json 메타 병합
                                            ◀── [{name, size, keywords, vlm_text, timestamp}, ...]
  → UI에 새 클립 표시
```

핵심: **app이 직접 "새 클립이 생겼다"는 알림을 보내지 않는다.** SSE의 `clip_count`가 바뀐 것을 보고 Browser가 스스로 api에 목록을 다시 묻는 폴링 모델이다 ([useClips.js:42](web/src/composables/useClips.js#L42)).

---

## Phase 8. 클립 재생 / 삭제

재생:
```
Browser <video src="http://host:8000/clips/{name}?token=...&s=...">
        ──GET with Range: bytes=START-END──▶ api
                                              └─ resolve_clip_path → /data/YYYY/MM/{name}
                                                 parse_byte_range
                                              ◀── 206 Partial Content (스트리밍)
```

api의 [main.py:306](api/main.py#L306) `get_clip()`이 HTTP Range를 지원하므로 영상 탐색이 가능하다. 토큰은 쿼리스트링으로 전달(`<video>` 태그는 헤더를 못 붙임).

삭제:
```
Browser ──DELETE /clips {names:[...]}──▶ api  ([api/main.py:344])
                                          ├─ 각 파일 unlink + .json unlink
                                          └─ deleted 개수 응답
```

api·app 양쪽 모두 같은 `/data` 볼륨을 보고 있으므로 어느 쪽에서 지워도 일관된다. 단 app 측에도 `/clips DELETE`가 있고([server.py:412](app/server.py#L412)) 둘이 거의 같은 일을 한다 — 단일 카메라 가정 위에 둔 의도적 중복으로 보인다.

---

## 한 줄로 요약

**Browser가 자격증명을 api에 넘기면 api가 app에 프록시하고 app이 mtx를 카메라에 물린다. 그 순간부터 mtx의 `live` 경로 하나를 (1) GStreamer가 1fps로 빨아 VLM에 넣고, (2) 별도 ffmpeg가 1초 단위 세그먼트로 tmpfs에 쌓고, (3) Browser가 HLS/WebRTC로 본다. VLM이 키워드를 매칭하면 (1)에서 알아낸 시각을 기준으로 (2)의 세그먼트들을 잘라 붙여 한 mp4로 저장하고, app은 SSE로 `clip_count`만 알려서 Browser가 api에 목록을 다시 묻게 한다.**

이 흐름의 미묘한 부분 — 가령 "왜 라이브 뷰는 mtx 직통인데 추론 입력은 app이 한 번 더 받아오는가", "왜 app은 클립 알림을 SSE의 카운트 변화로만 신호하는가" 같은 — 은 설계 의도에 부합하는지 확인이 필요한 지점일 수 있다.

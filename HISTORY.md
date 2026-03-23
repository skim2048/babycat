# 개발 히스토리

---

## 260309 — 설계 검토 (README v0.4)

### 주요 결정

**Branch A 패스스루 확정**
- 기존: `rtspsrc → DEC → TEE → NVENC → MediaMTX` (불필요한 재인코딩)
- 확정: MediaMTX가 카메라를 직접 pull. GStreamer는 Branch B(AI)만 처리

**컨테이너 구성 확정**
- App (GStreamer + NanoLLM) / MediaMTX / API 서버 (SQLite 내장) — 3개

**Ring Buffer 설계**
- 단일 버퍼로 VLM 추론 입력 + 소급 저장 윈도우 겸용
- 크기 = max(VLM 추론 윈도우, 소급 저장 윈도우)

**VILA1.5-3b 멀티프레임 지원 확인**
- Orin NX 16GB 기준 최대 8프레임 권장
- SigLIP 384×384 리사이즈 → 입력 해상도는 추론 시간에 무관

**샘플링 파라미터 (OI-02, OI-03) 결정 보류** — 실측 데이터 기반으로 결정 예정

---

## 260310 — Phase 0: 파이프라인 검증 및 Dockerfile 완성

### GStreamer 파이프라인 실측 (JetPack 6.2, Orin NX 16GB)

```
rtspsrc → rtph264depay → h264parse → nvv4l2decoder
→ nvvidconv (RGBA) → videorate → appsink
```

| 항목 | 결과 |
|---|---|
| 해상도 | 1920×1080, RGBA, 7.91 MB/frame |
| appsink FPS | 25.4 FPS |
| 필수 패키지 | `nvidia-l4t-gstreamer`, `gstreamer1.0-plugins-bad` |

**JetPack 6.2 변경사항**: `nvvideoconvert` → `nvvidconv` 명칭 변경. `rtspclientsink` 미지원 확인.

### VLM 벤치마크 (VILA1.5-3b, q4f16_ft, MLC)

| 프레임 수 | 추론 시간 |
|---|---|
| 1 | ~1,066 ms |
| 4 | ~4,027 ms |
| 8 | ~7,522 ms |

GPU 메모리: 7.4 GB. 추론 시간은 프레임 수에 선형 비례.

**OI-01 확정**: VILA1.5-3b (7.4GB RAM, ~1s/frame).

**NanoLLM 올바른 API** (ChatHistory):
```python
chat = ChatHistory(model)
chat.append('user', image=img)
chat.append('user', text=prompt)
embedding, _ = chat.embed_chat()
for token in model.generate(embedding, max_new_tokens=32, streaming=True): ...
chat.reset(); gc.collect()  # 메모리 누수 방지 (issue #39)
```

### videorate FPS 정규화 채택

`nvvidconv → videorate(target_fps) → appsink` — 카메라 FPS 무관하게 균일 샘플링

### Ring Buffer 역할 재정의

링버퍼는 VLM 추론 전용으로 단순화. 클립 저장은 MediaMTX 세그먼트 레코딩으로 분리:
- 60초 단위 fmp4 세그먼트 순환 저장 → 이벤트 발생 시 App이 events/ 디렉토리로 복사

### Dockerfile 완성

`dustynv/nano_llm:r36.4.0` 베이스. NVIDIA GStreamer 플러그인은 런타임 볼륨 마운트 (`/usr/lib/aarch64-linux-gnu/gstreamer-1.0`). `kmod` 포함 필수 (아래 참고).

---

## 260316~17 — Phase 1: main.py 완성 + E2E 검증

### nvv4l2decoder 컨테이너 이슈 해결

**증상**: 컨테이너 내 `S_EXT_CTRLS for CUDA_GPU_ID failed`, 프레임 타임아웃

**원인**: `libgstnvvideo4linux2.so`가 내부적으로 `lsmod | grep nvgpu` 실행 → `lsmod` 없으면 cuvidv4l2 경로 선택 → Jetson iGPU에 없는 `libnvidia-encode.so` 요구 → EINVAL

**해결**: Dockerfile에 `kmod` 추가 (lsmod 제공)

> **핵심**: 컨테이너에서 nvv4l2decoder 실패 시 디바이스/라이브러리가 아닌 **`lsmod` 유무**를 먼저 확인.

시행착오 (전부 실패): 개별 디바이스 노드 마운트, `/dev:/dev` 전체 마운트, `--privileged`, `ipc: host`, 라이브러리 마운트 제거.

### 추론 속도 1700ms (기준 1500ms 초과)

원인: CLIP TensorRT 비활성화 (16GB < 20GB 하드코딩 임계값) → Transformers 폴백
- `clip_trt/vision.py`: `if psutil.virtual_memory().total < 20 * (1024**3): return`
- Jetson Orin NX 16GB 환경에서 구조적으로 미지원. **1700ms를 실용 기준으로 수용.**

### main.py 구조

| 컴포넌트 | 역할 |
|---|---|
| `RingBuffer` | VLM 컨텍스트용 순환 버퍼. GStreamer 콜백(스레드)에서 push, 추론 스레드에서 latest() |
| `EventJudge` | CONSEC_N 연속 감지 시 알림 발령. 다른 결과 수신 시 streak 초기화 |
| `run_inference()` | NanoLLM ChatHistory API 멀티모달 추론 |
| `parse_vlm_response()` | `DETECTED: <key>` → 행동 키, 그 외 → None. EOS 토큰 제거, "none" 키 무시 |
| `send_alert()` | FCM HTTP v1 API 발송 + preserve_clip 비동기 실행 |
| `preserve_clip()` | MediaMTX 세그먼트 최신 N개를 events/ 디렉토리로 복사 |
| `inference_worker()` | 별도 스레드. infer_queue 신호 → ring.latest() → 추론 → 판정 → 알림 |

### E2E 통합 테스트: 12/12 PASS

EventJudge (6), preserve_clip (4), send_alert (2) — GStreamer/VLM 없이 비즈니스 로직 검증.

### VILA1.5-3b 포맷 지시 미준수 특성

엄격한 출력 포맷(DETECTED/NORMAL) 지시를 잘 따르지 못함. 자유 서술 방식이 더 나은 결과. 프로덕션 프롬프트 설계 시 반영 필요.

---

## 260319 — 파이프라인 점검 + 디버그 대시보드 + ONVIF PTZ

### 디버그 대시보드 (`app/debug_server.py`)

Python stdlib만 사용 (외부 의존성 없음).

| 엔드포인트 | 역할 |
|---|---|
| `GET /` | HTML 대시보드 (아코디언: Inference / Pipeline / Hardware / Pan&Tilt / Events) |
| `GET /stream` | MJPEG 스트림 (VLM 입력 384×384 프레임) |
| `GET /events` | SSE (추론 결과 + 하드웨어 상태 실시간) |
| `POST /ptz` | PTZ 제어 (move / stop / save / goto) |
| `POST /event` | 이벤트 테스트 (alert / clip) — 검증용 |

Live Stream: HLS (`http://<host>:8888/live/index.m3u8`, hls.js). WebRTC는 Docker 내부 ICE 후보 문제로 제외.

### ONVIF PTZ (카메라 192.168.1.101:2020)

| 지원 | 미지원 |
|---|---|
| AbsoluteMove, RelativeMove, ContinuousMove | Zoom, HomeSupported |
| Preset (최대 8개) | |
| Pan/Tilt 범위 -1.0 ~ +1.0 | |

인증: WS-Security PasswordDigest. 외부 라이브러리 없이 `urllib.request`로 SOAP 직접 구현.

`ptz_home.txt` 포맷: `pan=0.22 / tilt=-0.553`. 2초 폴링 루프로 현재 위치 갱신.

### VLM 신뢰도 표시 시도 → 롤백

VILA1.5-3b가 `CONFIDENCE:XX` 포맷 지시 미준수. 언어 기반 휴리스틱도 실 영상 없어 검증 불가. 전량 롤백.

### 멀티프레임 (N_FRAMES=4): 추론 4200ms

VILA1.5-3b는 진정한 temporal encoder 없음 (multi-image를 LLM 텍스트 추론으로 처리). 대안: Qwen2.5-VL-3B (mRoPE temporal 처리). 실 영상 확보 후 재검토.

---

## 260321 — 모노레포 구조 개편 + 프론트엔드 뼈대 (v1.4)

디렉토리 변경: `backend/` → `server/`, `frontend/` → `webapp/`, `docs/` → `journal/`. docker-compose.yml 루트로 이동.

프론트엔드 (Vue 3 + nginx): Figma export 절대 픽셀 레이아웃 → flexbox 반응형으로 수정. `webapp/` 서비스는 `prod`/`dev` profile로 분리.

---

## 260323 — 범용 시스템 전환 + 구조 재편 + 이벤트 검증 (v1.5)

### 범용 시스템으로 방향 전환

반려견 특화 요소는 `BEHAVIORS` dict와 프롬프트 문자열뿐. 나머지는 도메인 무관. 감지 조건을 설정 파일/UI에서 주입할 수 있도록 범용화. Wally는 이 시스템 위의 파생 프로젝트로 구성.

### 디렉토리 재편

`server/src/app/` → `app/` (납작하게). `webapp/` 제거 (Wally 파생에서 별도 구성).

### 이벤트 검증 기능 (디버그 대시보드 EVENTS 섹션)

`send_alert()` / `preserve_clip()` 수동 트리거 및 결과 확인. `main.py → DebugState` 단방향 콜백으로 연결 (TODO: 리팩토링 시 의존성 역전 고려).

`POST /event` 명세:

| action | 동작 |
|---|---|
| `alert` + `behavior` | `send_alert(behavior)` 호출 |
| `clip` + `behavior` | `preserve_clip(behavior, now)` 호출 |

---

## 미결 항목

| # | 항목 | 비고 |
|---|---|---|
| OI-02 | 프레임 샘플링 주기 (TARGET_FPS, N_FRAMES) | 현재 1fps / 4프레임. 실 영상 기반 결정 필요 |
| OI-03 | 연속 감지 조건 (CONSEC_N) | 현재 3회. 오탐율 실험 후 결정 |
| OI-04 | Ring Buffer 크기 | 현재 30프레임 |
| OI-10 | PTZ 중 VLM 추론 억제 | PTZ 제어 완료. 억제 로직은 미결 |
| — | 감지 조건 외부화 | 설정 파일/UI 주입 — 소프트웨어 v1.1 목표 |
| — | API 서버 구현 | 미착수 |
| — | 클라이언트 앱 (Android) | 미착수 |

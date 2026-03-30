# Babycat

> **목적**: 카메라 영상을 사용자가 정의한 조건에 따라 실시간으로 분석하는 엣지 AI 백엔드.
> **버전**: v1.8

| 버전 | 변경 내용 |
|---|---|
| v0.1 | 최초 작성 |
| v0.2 | 파이프라인 아키텍처 초안 (Tee 분리 모델, Ring Buffer, 실시간 스트리밍, Docker 컨테이너 구성) |
| v0.3 | 프로젝트명 변경 |
| v0.4 | 파이프라인 다이어그램 Mermaid 전환 |
| v0.5 | Branch A 패스스루 구조 확정, API 서버·DB 컨테이너 추가, OI 업데이트 |
| v0.6 | 컨테이너 통합 (App+NanoLLM → App, DB → API 서버 내장 SQLite), OI-08 확정 |
| v0.7 | Branch A: GStreamer tee 제거, MediaMTX 직접 pull 구조로 변경. GStreamer는 Branch B(AI)만 처리 |
| v0.8 | Branch B videorate 복원 (FPS 정규화). 프레임 샘플링 전략 및 gc.collect() 주의사항 추가 |
| v0.9 | Ring Buffer 역할 재정의 (VLM 추론 전용). 클립 저장을 MediaMTX 세그먼트 녹화로 이전 |
| v1.0 | Phase 1 완료: FCM 알림(stub), 영상 클립 보존(preserve_clip), E2E 통합 테스트(12/12 PASS) |
| v1.1 | nvv4l2decoder 컨테이너 HW 디코더 활성화. VLM 파이프라인 검증 (추론 ~1700ms 실측) |
| v1.2 | 전체 파이프라인 재점검. 디버그 대시보드 구축 (MJPEG 스트림 · SSE 추론 결과 · 하드웨어 모니터) |
| v1.3 | ONVIF PTZ 검증 및 제어 구현 (ContinuousMove · AbsoluteMove · 홈 위치 저장). 디버그 대시보드에 PTZ UI 통합 |
| v1.4 | 모노레포 디렉토리 개편 (backend→server, frontend→webapp, docs→journal). 프론트엔드 UI 뼈대 구성 |
| v1.5 | 범용 시스템으로 방향 전환. 디렉토리 구조 재편 (server/src/app→app, webapp 제거). 저널 파일명 패턴 정리 |
| v1.6 | 브라우저 프롬프트/트리거 키워드 입력 UI. 이벤트 감지 시 ffmpeg 직접 녹화 클립 저장 (5s, 30s 쿨다운). MediaMTX 세그먼트 10s로 단축 |
| v1.7 | 이벤트 클립 좌측 수직 사이드바로 재배치. 클립 검색·선택삭제·모두삭제·개별삭제. 커스텀 미디어 플레이어 컨트롤. LIVE STREAM 잔여 높이 동적 채움(letterbox). 브라우저 로딩 스피너 제거 |
| v1.8 | API 서버 구현 (FastAPI, SQLite). 클립·이벤트·기기토큰 REST API. PTZ 이동 중 VLM 추론 억제 (OI-10). API 레퍼런스 문서 |

---

## 1. 프로젝트 목적

RTSP 스트림을 입력으로 받아 VLM(Visual Language Model) 추론을 수행하고, 사용자가 정의한 조건이 감지되면 FCM 푸시 알림을 전송한다.

- 입력: RTSP 카메라 스트림 (H.264)
- 감지 조건: 사용자가 UI 또는 설정 파일로 지정한 시각적 조건
- 알림 수단: FCM (Android 앱)
- 부가 기능: 실시간 스트리밍, 이벤트 클립 보존, PTZ 제어

---

## 2. 하드웨어 구성

| 구성 요소 | 사양 | 비고 |
|---|---|---|
| Edge AI 보드 | NVIDIA Jetson Orin NX 16GB | GPU+CPU 통합 메모리 16GB |
| 카메라 | IR 지원 IP Camera | RTSP 스트림, H.264 |
| 네트워크 | 유선 이더넷 권장 | Wi-Fi는 스트림 지연 위험 |

**제약사항**:
- Jetson Orin NX 16GB는 CPU/GPU 통합 메모리 구조 — VLM 모델 크기가 전체 메모리 가용량에 직접 영향
- 외부 클라우드 추론 서버 없음 — Jetson 단독 처리 (엣지 완결형)

---

## 3. 디렉토리 구조

```
/
├── app/          # GStreamer 파이프라인 · VLM 추론 · FCM 알림
├── config/       # mediamtx.yml 등 서비스 설정
├── docker/       # Dockerfile (app, api)
├── tests/        # 단위·통합·벤치마크 테스트
├── docker-compose.yml
└── README.md
```

---

## 4. 시스템 아키텍처

### 4.1 컨테이너 구성

| 컨테이너 | 역할 |
|---|---|
| App | GStreamer 파이프라인, VLM 추론, 이벤트 판정, FCM 발송 |
| MediaMTX | RTSP/WebRTC 스트리밍 서버 (Branch A 패스스루 + 세그먼트 녹화) |
| API 서버 | 기기 토큰 등록, 이벤트 이력 조회, 영상 클립 제공 (SQLite 내장) |

### 4.2 파이프라인 아키텍처

``` mermaid
flowchart TD
    CAM["IP Camera\n(IR 지원, RTSP)"]

    subgraph JETSON["Jetson Orin NX 16GB"]

        subgraph MEDIAMTX["MediaMTX 컨테이너"]
            MTX["RTSP/WebRTC\n스트리밍 서버"]
            REC["세그먼트 녹화\n(순환 저장, 공유 볼륨)"]
        end

        subgraph APP["App 컨테이너\n(GStreamer + NanoLLM + Python)"]
            subgraph GST["GStreamer Pipeline (Branch B)"]
                SRC["rtspsrc"]
                DEC["nvv4l2decoder\n(GPU HW 디코딩)"]
                CONV["nvvidconv\n(RGBA 변환)"]
                RATE["videorate\n(FPS 정규화)"]
                SINK["appsink"]
            end

            subgraph PYAPP["Python Application"]
                RING["Ring Buffer"]
                VLM["VLM 추론\n(NanoLLM/VILA)"]
                JUDGE["이벤트 판정\n(사용자 정의 조건)"]
            end
        end
    end

    CAM -->|"RTSP (H.264)"| MTX
    MTX -->|"실시간 스트림"| CLIENT["클라이언트 (Android 앱)"]
    MTX -->|"세그먼트 기록"| REC
    MTX -->|"RTSP (내부)"| SRC
    SRC --> DEC --> CONV --> RATE --> SINK
    SINK --> RING --> VLM --> JUDGE
    JUDGE -->|"이상 감지"| REC
    JUDGE -->|"알림 발송"| FCM["FCM"] --> CLIENT
```

**Branch A — 실시간 스트리밍**: MediaMTX가 카메라 RTSP를 직접 pull → 클라이언트에 재배포. GStreamer 개입 없음.

**Branch B — AI 분석**: GStreamer가 MediaMTX에서 스트림을 읽어 GPU 디코딩 → VLM 추론 → 이벤트 판정.

**클립 저장**: 이벤트 감지 시 ffmpeg로 RTSP 스트림에서 5초간 직접 녹화 (mp4, 비디오 copy + 오디오 aac). 30초 쿨다운으로 중복 방지.

### 4.3 설계 원칙

- 엣지 완결형 — Jetson 단독 처리, 외부 추론 서버 없음
- GPU 디코딩(nvv4l2decoder) 기본 사용
- 감지 조건은 브라우저 UI에서 실시간 주입 — VLM 프롬프트 및 트리거 키워드 동적 변경 가능

---

## 5. 소프트웨어 스택

### 5.1 VLM 추론

| 구성 요소 | 내용 |
|---|---|
| 런타임 | NanoLLM (dustynv/jetson-containers) |
| 모델 | VILA1.5-3b (기본), 교체 가능 |
| 추론 속도 | ~4200ms / 추론 (Jetson Orin NX 16GB, TensorRT) |

### 5.2 영상 파이프라인

- GStreamer + nvv4l2decoder (GPU HW 디코딩)
- nvvidconv (포맷 변환)
- MediaMTX (RTSP/HLS/WebRTC 스트리밍 서버)

### 5.3 알림 인프라

- FCM HTTP v1 API (서비스 계정 기반 OAuth 2.0)

---

## 6. 주요 기술 리스크

| 리스크 | 내용 | 대응 방향 |
|---|---|---|
| 메모리 부족 (OOM) | VLM + Ring Buffer + 영상 파이프라인이 16GB 통합 메모리 경합 | 컴포넌트별 메모리 예산 설계, 모델 양자화(INT4/INT8) |
| 추론 지연 | VLM 추론 수 초 소요 — 감지 반응성에 영향 | TensorRT 최적화, 샘플링 주기 조정 |
| 파이프라인 블로킹 | appsink 지연 시 GStreamer 파이프라인 정지 위험 | drop=true, max-buffers 제한으로 오래된 프레임 강제 폐기 |
| VLM 오탐율 | 조건 해석 모호성 | 연속 감지 조건, 신뢰도 임계값 튜닝 |
| 야간 화질 | IR 영상에서 VLM 정확도 저하 가능성 | IR 영상 기반 별도 검증 |

---

## 7. 미결 사항 (Open Issues)

| # | 항목 | 상태 |
|---|---|---|
| OI-02 | 프레임 샘플링 주기 (Branch B FPS) | 미결 (현재 1fps) |
| OI-03 | 연속 감지 조건 기준값 (CONSEC_N) | 미결 (현재 3회, 튜닝 필요) |
| OI-04 | Ring Buffer 크기 | 30프레임(30s @1fps) 기본값, 실험 후 조정 |
| OI-07 | 클라이언트 앱 | 미결 |
| OI-10 | ONVIF PTZ 제어 — 추론 억제 연동 | 미결 |

---

## 8. 실행 계획

### 완료
- [x] GStreamer 파이프라인 (GPU 디코딩)
- [x] VLM 추론 (VILA1.5-3b, TensorRT)
- [x] 이벤트 판정 로직 (EventJudge)
- [x] FCM 알림 (stub)
- [x] 영상 클립 보존 (preserve_clip)
- [x] E2E 통합 테스트 (12/12 PASS)
- [x] ONVIF PTZ 제어
- [x] 디버그 대시보드 (MJPEG · SSE · PTZ)

### 예정
- [x] 감지 조건 외부화 — 브라우저 UI에서 프롬프트/트리거 키워드 실시간 주입
- [x] 이벤트 클립 저장 — ffmpeg 직접 녹화 (5s, 30s 쿨다운)
- [x] API 서버 구현 (FastAPI, SQLite) — 클립·이벤트·기기토큰 REST API
- [x] PTZ 이동 중 VLM 추론 억제 (OI-10)
- [ ] 클라이언트 앱 (Android) — 실시간 스트리밍, 이벤트 이력, 알림 수신

---

## 9. 용어 정의

| 용어 | 정의 |
|---|---|
| 엣지 완결형 | 외부 서버 없이 Jetson 단독으로 감지~알림 전 처리를 수행하는 구조 |
| 연속 감지 조건 | 단발성 오탐을 방지하기 위해 N회 연속 감지 시에만 알림을 발송하는 조건 |
| 통합 메모리 | Jetson Orin NX의 CPU와 GPU가 물리적으로 동일한 메모리 풀을 공유하는 구조 |
| Ring Buffer | 최근 N초 분량의 프레임을 순환 구조로 메모리에 유지하는 버퍼 |
| Branch A | MediaMTX가 카메라를 직접 pull하여 클라이언트에 재배포하는 스트리밍 경로 |
| Branch B | GStreamer가 MediaMTX에서 스트림을 읽어 GPU 디코딩 후 AI 분석을 수행하는 경로 |
| VLM | Visual Language Model. 이미지와 텍스트를 함께 처리하는 멀티모달 언어 모델 |
| FCM | Firebase Cloud Messaging. Google의 크로스 플랫폼 푸시 알림 인프라 |

---

## 10. 개발 히스토리

### 260309 — 설계 검토 (README v0.4)

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

### 260310 — Phase 0: 파이프라인 검증 및 Dockerfile 완성

#### GStreamer 파이프라인 실측 (JetPack 6.2, Orin NX 16GB)

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

#### VLM 벤치마크 (VILA1.5-3b, q4f16_ft, MLC)

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

#### videorate FPS 정규화 채택

`nvvidconv → videorate(target_fps) → appsink` — 카메라 FPS 무관하게 균일 샘플링

#### Ring Buffer 역할 재정의

링버퍼는 VLM 추론 전용으로 단순화. 클립 저장은 MediaMTX 세그먼트 레코딩으로 분리:
- 60초 단위 fmp4 세그먼트 순환 저장 → 이벤트 발생 시 App이 events/ 디렉토리로 복사

#### Dockerfile 완성

`dustynv/nano_llm:r36.4.0` 베이스. NVIDIA GStreamer 플러그인은 런타임 볼륨 마운트 (`/usr/lib/aarch64-linux-gnu/gstreamer-1.0`). `kmod` 포함 필수 (아래 참고).

---

### 260316~17 — Phase 1: main.py 완성 + E2E 검증

#### nvv4l2decoder 컨테이너 이슈 해결

**증상**: 컨테이너 내 `S_EXT_CTRLS for CUDA_GPU_ID failed`, 프레임 타임아웃

**원인**: `libgstnvvideo4linux2.so`가 내부적으로 `lsmod | grep nvgpu` 실행 → `lsmod` 없으면 cuvidv4l2 경로 선택 → Jetson iGPU에 없는 `libnvidia-encode.so` 요구 → EINVAL

**해결**: Dockerfile에 `kmod` 추가 (lsmod 제공)

> **핵심**: 컨테이너에서 nvv4l2decoder 실패 시 디바이스/라이브러리가 아닌 **`lsmod` 유무**를 먼저 확인.

시행착오 (전부 실패): 개별 디바이스 노드 마운트, `/dev:/dev` 전체 마운트, `--privileged`, `ipc: host`, 라이브러리 마운트 제거.

#### 추론 속도 1700ms (기준 1500ms 초과)

원인: CLIP TensorRT 비활성화 (16GB < 20GB 하드코딩 임계값) → Transformers 폴백
- `clip_trt/vision.py`: `if psutil.virtual_memory().total < 20 * (1024**3): return`
- Jetson Orin NX 16GB 환경에서 구조적으로 미지원. **1700ms를 실용 기준으로 수용.**

#### main.py 구조

| 컴포넌트 | 역할 |
|---|---|
| `RingBuffer` | VLM 컨텍스트용 순환 버퍼. GStreamer 콜백(스레드)에서 push, 추론 스레드에서 latest() |
| `EventJudge` | CONSEC_N 연속 감지 시 알림 발령. 다른 결과 수신 시 streak 초기화 |
| `run_inference()` | NanoLLM ChatHistory API 멀티모달 추론 |
| `parse_vlm_response()` | `DETECTED: <key>` → 행동 키, 그 외 → None. EOS 토큰 제거, "none" 키 무시 |
| `send_alert()` | FCM HTTP v1 API 발송 + preserve_clip 비동기 실행 |
| `preserve_clip()` | MediaMTX 세그먼트 최신 N개를 events/ 디렉토리로 복사 |
| `save_trigger_clip()` | 트리거 이벤트 시 ffmpeg로 RTSP에서 5초 직접 녹화 (30s 쿨다운) |
| `inference_worker()` | 별도 스레드. infer_queue 신호 → ring.latest() → 추론 → 판정 → 알림 |

#### E2E 통합 테스트: 12/12 PASS

EventJudge (6), preserve_clip (4), send_alert (2) — GStreamer/VLM 없이 비즈니스 로직 검증.

#### VILA1.5-3b 포맷 지시 미준수 특성

엄격한 출력 포맷(DETECTED/NORMAL) 지시를 잘 따르지 못함. 자유 서술 방식이 더 나은 결과. 프로덕션 프롬프트 설계 시 반영 필요.

---

### 260319 — 파이프라인 점검 + 디버그 대시보드 + ONVIF PTZ

#### 디버그 대시보드 (`app/debug_server.py`)

Python stdlib만 사용 (외부 의존성 없음).

| 엔드포인트 | 역할 |
|---|---|
| `GET /` | HTML 대시보드 (아코디언: Inference / Pipeline / Hardware / Pan&Tilt / Events) |
| `GET /stream` | MJPEG 스트림 (VLM 입력 384×384 프레임) |
| `GET /events` | SSE (추론 결과 + 하드웨어 상태 실시간) |
| `POST /ptz` | PTZ 제어 (move / stop / save / goto) |
| `POST /prompt` | VLM 프롬프트 및 트리거 키워드 변경 |
| `POST /event` | 이벤트 테스트 (alert / clip) — 검증용 |

Live Stream: HLS (`http://<host>:8888/live/index.m3u8`, hls.js). WebRTC는 Docker 내부 ICE 후보 문제로 제외.

#### ONVIF PTZ (카메라 192.168.1.101:2020)

| 지원 | 미지원 |
|---|---|
| AbsoluteMove, RelativeMove, ContinuousMove | Zoom, HomeSupported |
| Preset (최대 8개) | |
| Pan/Tilt 범위 -1.0 ~ +1.0 | |

인증: WS-Security PasswordDigest. 외부 라이브러리 없이 `urllib.request`로 SOAP 직접 구현.

`ptz_home.txt` 포맷: `pan=0.22 / tilt=-0.553`. 2초 폴링 루프로 현재 위치 갱신.

#### VLM 신뢰도 표시 시도 → 롤백

VILA1.5-3b가 `CONFIDENCE:XX` 포맷 지시 미준수. 언어 기반 휴리스틱도 실 영상 없어 검증 불가. 전량 롤백.

#### 멀티프레임 (N_FRAMES=4): 추론 4200ms

VILA1.5-3b는 진정한 temporal encoder 없음 (multi-image를 LLM 텍스트 추론으로 처리). 대안: Qwen2.5-VL-3B (mRoPE temporal 처리). 실 영상 확보 후 재검토.

---

### 260321 — 모노레포 구조 개편 + 프론트엔드 뼈대 (v1.4)

디렉토리 변경: `backend/` → `server/`, `frontend/` → `webapp/`, `docs/` → `journal/`. docker-compose.yml 루트로 이동.

프론트엔드 (Vue 3 + nginx): Figma export 절대 픽셀 레이아웃 → flexbox 반응형으로 수정. `webapp/` 서비스는 `prod`/`dev` profile로 분리.

---

### 260323 — 범용 시스템 전환 + 구조 재편 + 이벤트 검증 (v1.5)

#### 범용 시스템으로 방향 전환

기존 도메인 특화 요소(`BEHAVIORS` dict, 하드코딩 프롬프트)를 제거하고 범용 시스템으로 전환. 감지 조건을 브라우저 UI에서 주입할 수 있도록 범용화.

#### 디렉토리 재편

`server/src/app/` → `app/` (납작하게). `webapp/` 제거 (파생 프로젝트에서 별도 구성).

#### 이벤트 검증 기능 (디버그 대시보드 EVENTS 섹션)

`send_alert()` / `preserve_clip()` 수동 트리거 및 결과 확인. `main.py → DebugState` 단방향 콜백으로 연결 (TODO: 리팩토링 시 의존성 역전 고려).

`POST /event` 명세:

| action | 동작 |
|---|---|
| `alert` + `detected` | `send_alert(detected)` 호출 |
| `clip` + `detected` | `preserve_clip(detected, now)` 호출 |

---

### 260325 — 브라우저 프롬프트/트리거 UI + ffmpeg 클립 녹화 (v1.6)

#### 브라우저 프롬프트/트리거 키워드 입력

대시보드 LIVE STREAM 아래에 두 개의 텍스트 필드 추가:
- **프롬프트 필드**: VLM 추론에 사용할 사전 프롬프트 입력
- **트리거 키워드 필드**: 쉼표 구분 키워드 입력. VLM 출력에 키워드가 포함되면 이벤트 발생

"적용" 버튼으로 양쪽 모두 반영. SSE로 초기값 동기화. Inference 섹션 배경색: 녹색(정상) / 붉은색(이벤트 감지).

#### 이벤트 클립 저장: 세그먼트 복사 → ffmpeg 직접 녹화

기존 방식(MediaMTX 세그먼트 복사)은 세그먼트 경계에 의존하여 클립 길이가 불확정. ffmpeg로 이벤트 시점부터 RTSP 스트림에서 5초간 직접 녹화하는 방식으로 변경.

- 포맷: mp4 (비디오 copy + 오디오 aac)
- 쿨다운: 30초 (중복 녹화 방지)
- 별도 데몬 스레드에서 실행 (추론 스레드 블로킹 방지)

#### MediaMTX 세그먼트 10s로 단축

`recordSegmentDuration: 60s → 10s`. preserve_clip용 `CLIP_PRE_SEGMENTS: 2 → 1`.

---

### 260326 — 이벤트 클립 사이드바 + 대시보드 레이아웃 개선 (v1.7)

#### EVENT CLIPS 좌측 수직 사이드바로 재배치

기존 하단 수평 갤러리 방식에서 좌측 수직 사이드바(260px)로 변경. 최신 클립이 상단에 위치하도록 역순 정렬.

레이아웃: `[Event Clips 사이드바] | [Live Stream + Prompting] | [Dashboard 사이드바]`

#### 클립 관리 기능 추가

| 기능 | 내용 |
|---|---|
| 검색 필터 | 파일명 기준 키워드 실시간 필터링 |
| 개별 삭제 | 클립 상단 ✕ 버튼 |
| 선택 삭제 | 체크박스 선택 후 "선택 삭제" |
| 모두 삭제 | "모두 삭제" 버튼 |

#### 클립 커스텀 미디어 플레이어

각 클립 항목에 재생/일시정지 버튼, 프로그레스 바(클릭 탐색), 경과/전체 시간 표시 적용.

#### LIVE STREAM 동적 높이 및 letterbox

LIVE STREAM이 `viewport 높이 - (topbar + Prompting)` 공간을 채우도록 flex 레이아웃 조정. 종횡비는 `object-fit: contain`으로 유지(letterbox).

#### 브라우저 로딩 스피너 제거

MJPEG 스트림(`<img src="/stream">`)의 `src`를 HTML에서 제거하고 `window.load` 이후 JS로 지연 설정. 탭 파비콘 스피너 및 하단 상태표시줄 "전송중" 메시지 해소.

#### 클립 파일 서빙 query string 버그 수정

`GET /clip/<name>` 처리 시 `?s=...` cache buster query string을 `urlparse`로 분리하여 404 오류 수정.

---

### 260330 — API 서버 구현 + PTZ 추론 억제 (v1.8)

#### API 서버 (FastAPI + SQLite)

`api/` 디렉토리에 REST API 서버 구현. App 컨테이너의 퍼시스턴트 데이터(클립, 이벤트, 기기 토큰)를 분리.

| 파일 | 역할 |
|---|---|
| `api/main.py` | FastAPI 엔드포인트 (11개) |
| `api/database.py` | SQLite 초기화 (WAL 모드), events·devices 테이블 |
| `api/schemas.py` | Pydantic 요청/응답 스키마 |

엔드포인트: `/health`, `/clips` (목록·다운로드·선택삭제·전체삭제), `/events` (조회·기록·삭제), `/devices` (목록·등록/갱신·삭제). 클립 파일 다운로드는 Range 요청 지원 (브라우저 `<video>` 재생).

클립 공유: App 컨테이너가 `./app/clip`에 ffmpeg로 쓰고, API 서버가 같은 호스트 경로를 `/data/clips`로 마운트하여 서빙.

docker-compose: `profiles: [api]` 제거 (기본 시작), 환경변수 `CLIP_DIR`·`DB_PATH` 설정.

테스트: `tests/test_api.py` — 23개 테스트 (23/23 PASS).

#### PTZ 이동 중 VLM 추론 억제 (OI-10)

`ContinuousMove` 중 VLM 추론을 건너뛰도록 구현. PTZ 이동 중 카메라 화면이 흔들려 추론 결과가 무의미하기 때문.

- `debug_server.py`: `_ptz_moving` 플래그 추가. `move` → True, `stop` → False.
- `main.py`: `inference_worker`가 매 루프에서 `ptz_is_moving()` 확인, True이면 `continue`.

`goto`(AbsoluteMove)는 억제하지 않음 — 카메라가 자체적으로 이동 완료 후 정지.

#### API 레퍼런스 문서

`docs/api.md` — 프론트엔드 개발자용 통합 API 레퍼런스. 3개 서비스(MediaMTX, App, API Server)의 전체 엔드포인트, 요청/응답 스키마, SSE 데이터 형식, 프론트엔드 코드 예시 포함.

---

### 미결 항목

| # | 항목 | 비고 |
|---|---|---|
| OI-02 | 프레임 샘플링 주기 (TARGET_FPS, N_FRAMES) | 현재 1fps / 4프레임. 실 영상 기반 결정 필요 |
| OI-03 | 연속 감지 조건 (CONSEC_N) | 현재 3회. 오탐율 실험 후 결정 |
| OI-04 | Ring Buffer 크기 | 현재 30프레임 |
| ~~OI-10~~ | ~~PTZ 중 VLM 추론 억제~~ | ~~v1.8에서 완료 (ContinuousMove 중 추론 건너뜀)~~ |
| — | ~~감지 조건 외부화~~ | ~~v1.6에서 완료 (브라우저 UI 프롬프트/트리거)~~ |
| — | ~~API 서버 구현~~ | ~~v1.8에서 완료 (FastAPI, SQLite, 23/23 테스트 PASS)~~ |
| — | 클라이언트 앱 (Android) | 미착수 |

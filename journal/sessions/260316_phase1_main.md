# 세션 요약 — 260316 / Phase 1 시작: src/app/main.py 작성

이전 세션 파일: `260310_v0.9_bench_dockerfile.md`

---

## 1. 작업 내용

Phase 0에서 미완으로 남긴 `src/app/main.py`를 작성하여 Phase 1을 시작.

### 생성 파일

- `src/app/main.py`

---

## 2. main.py 구조

### 컴포넌트

| 클래스 / 함수 | 역할 |
|---|---|
| `RingBuffer` | VLM 컨텍스트용 순환 버퍼 (maxlen=RING_SIZE). GStreamer 콜백(다른 스레드)에서 push, 추론 스레드에서 latest() 호출. Lock으로 thread-safe 보장 |
| `EventJudge` | 연속 감지 조건 판정. 동일 행동이 CONSEC_N회 연속 감지 시 알림 발령. 다른 결과(NORMAL 포함) 시 streak 초기화 |
| `run_inference()` | NanoLLM ChatHistory API 사용 멀티모달 추론. gc.collect() 필수 (issue #39) |
| `parse_vlm_response()` | VLM 출력 파싱: 'DETECTED: <key>' → 행동 키, 그 외 → None |
| `send_alert()` | FCM 알림 발송. 현재 로그 출력만 (Phase 1 후반에 구현 예정) |
| `build_pipeline_str()` | Branch B GStreamer 파이프라인 문자열 생성. Fraction으로 framerate 분수 표현 |
| `make_frame_callback()` | appsink 'new-sample' 콜백 생성. RGBA numpy → PIL(384×384 RGB) → RingBuffer push → 추론 큐 신호 |
| `inference_worker()` | 별도 스레드. 추론 큐 신호 수신 → ring.latest(N_FRAMES) → VLM 추론 → EventJudge → send_alert |
| `main()` | 모델 로드 → 추론 스레드 시작 → GStreamer pipeline → GLib.MainLoop |

### GStreamer 파이프라인 (Branch B)

```
rtspsrc (MediaMTX) → rtph264depay → h264parse → nvv4l2decoder
→ nvvidconv (RGBA) → videorate (TARGET_FPS) → appsink (drop=true, max-buffers=1)
```

### 추론 흐름

```
[GStreamer 스레드]                    [추론 스레드]
  appsink 콜백                          infer_queue.get()
    → numpy(RGBA) → PIL(384×384)   →      ring.latest(N_FRAMES)
    → ring.push(img)                      run_inference(model, frames)
    → infer_queue.put_nowait()            EventJudge.update(behavior)
      (Full이면 drop — 추론 중)           → send_alert() if alert
```

---

## 3. 설계 결정 사항

### 스레딩 모델

- GStreamer 콜백은 GStreamer 내부 스레드에서 호출
- VLM 추론(~1초)을 콜백 안에서 실행하면 파이프라인 블로킹 발생
- **별도 추론 스레드 + Queue(maxsize=1)** 로 분리: 추론 중 신규 프레임은 큐에 들어가지 않고 drop

### videorate FPS 표현

- `Fraction(target_fps).limit_denominator(1000)` 사용
- 정수 FPS(1.0 → `1/1`)뿐 아니라 분수 FPS(0.5 → `1/2`)도 정확히 표현

### 이미지 리사이즈 위치

- appsink 콜백에서 384×384 RGB로 즉시 리사이즈 후 RingBuffer 저장
- RingBuffer 메모리: 384×384×3 × 30프레임 ≈ **13MB** (RGBA 1080p 237MB 대비 대폭 절감)

---

## 4. 환경 변수 (런타임 튜닝)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MEDIAMTX_URL` | `rtsp://mediamtx:8554/live` | MediaMTX RTSP URL |
| `VLM_MODEL` | `Efficient-Large-Model/VILA1.5-3b` | NanoLLM 모델 ID |
| `TARGET_FPS` | `1.0` | Branch B videorate 타겟 FPS (OI-02) |
| `N_FRAMES` | `1` | 추론당 프레임 수 (OI-02) |
| `RING_SIZE` | `30` | RingBuffer 크기 (OI-04) |
| `CONSEC_N` | `3` | 연속 감지 임계값 (OI-03) |

---

## 5. 미결 항목 (Phase 1 진행 중)

| 항목 | 상태 | 비고 |
|---|---|---|
| OI-02 (TARGET_FPS, N_FRAMES) | 미결 | 실 반려동물 영상으로 측정 후 결정 |
| OI-03 (CONSEC_N) | 미결 | 오탐율 실험 후 결정 |
| FCM 알림 구현 | 미완 | `send_alert()` 현재 로그 출력만 |
| E2E 통합 테스트 | 미완 | 컨테이너 전체 기동 후 실 카메라 영상으로 검증 |
| VLM 정확도 검증 | 미완 | 실 반려동물 영상으로 7종 행동 감지 정확도 측정 |

---

## 6. 오늘 작업 요약 (2026-03-16)

- `src/app/main.py` 작성 (Phase 1 첫 번째 실행 파일)
- GStreamer Branch B 파이프라인 + 추론 스레드 + EventJudge + FCM stub 통합
- compose.yml/Dockerfile 변경 불필요 확인 (기존 live-mount 구성으로 바로 실행 가능)

---

## 7. 세션 2 추가 작업 (2026-03-17)

### 7.1 VLM Phase 1 검증 계획 수립

Phase 1 검증을 2단계로 분리 확정:

| 단계 | 목표 | 기준 |
|---|---|---|
| **Phase 1** | 파이프라인 정상 구동 + VLM 추론 속도 확인 | (1) 오류 없음, (2) 추론 500~1500ms |
| **Phase 2** | 정확도 검증 | 실 반려동물 행동 클립으로 7종 감지 정확도 측정 |

### 7.2 생성 파일

- `src/app/test_vlm_pipeline.py` — Phase 1 검증 스크립트

### 7.3 test_vlm_pipeline.py 구조

- VLM 모델 로드 (NanoLLM VILA1.5-3b, q4f16_ft)
- GStreamer 파이프라인 구동 (`rtspsrc → rtph264depay → h264parse → nvv4l2decoder → nvvidconv → appsink`)
- N_INFERENCES 회 추론 반복, 지연시간 측정
- PASS/FAIL 리포트: (1) 오류 횟수, (2) 평균 처리속도

환경 변수: `MEDIAMTX_URL`, `VLM_MODEL`, `N_INFERENCES`, `TARGET_FPS`

### 7.4 nvv4l2decoder 컨테이너 이슈

**증상**: 컨테이너 내 프레임 타임아웃 (5×10s 전부 실패)

**원인**: `VIDIOC_S_EXT_CTRLS` ioctl (`V4L2_CID_MPEG_VIDEO_CUDA_GPU_ID`) EINVAL 에러
- 호스트: `NvMMLiteOpen: Block: BlockType = 261` ✅ (HW 디코더 정상 초기화)
- 컨테이너: `S_EXT_CTRLS for CUDA_GPU_ID failed` ❌ (NvMMLite 초기화 불가)

**시도한 수정 내역**:

| 시도 | 결과 |
|---|---|
| nvmap, nvhost-ctrl-gpu 등 개별 디바이스 노드 추가 | 실패 |
| `ipc: host` 추가 (NvSciIPC POSIX shm) | 실패 |
| `/dev:/dev` 전체 마운트 | 실패 |
| `--privileged` | 실패 |
| `--network=host` | 실패 |
| nvidia lib 볼륨 마운트 제거 | 실패 |

**결론**: Phase 1용으로 `avdec_h264`(소프트웨어 디코더)로 교체 후 테스트 진행 예정. `nvv4l2decoder`는 프로덕션 성능 이슈로 Phase 1 이후 별도 해결.

### 7.5 compose.yml 수정 내역

| 변경 사항 | 이유 |
|---|---|
| 개별 디바이스 노드 → `/dev:/dev` 통합 마운트 | HW 디코더 접근 시도 (최종 미해결) |
| `ipc: host` 추가 | NvSciIPC POSIX shm/mqueue 공유 |
| 중복 `volumes:` 섹션 병합 | compose.yml 파싱 에러 수정 |

### 7.6 프론트엔드 회의 자료 생성

- `FRONT_SOURCE.md` — 프로젝트 미경험자용 프론트엔드 회의 자료
  - 시스템 전체 구조 (Mermaid)
  - 화면 흐름도 (Mermaid)
  - 화면별 스펙 (표 형식, 폰트 의존 레이아웃 제거)
- `FRONT_SOURCE.pdf` — weasyprint + Noto Sans KR 폰트로 생성 (220KB)

### 7.7 미결 항목 추가 (2026-03-17)

| 항목 | 상태 | 비고 |
|---|---|---|
| Phase 1 VLM 테스트 | ~~진행 중~~ → **완료** | 세션 8에서 해결 (아래 참고) |
| nvv4l2decoder 컨테이너 수정 | **완료** | kmod 설치로 해결 (세션 8) |
| FRONT_SOURCE.docx 변환 | 미완 | python-docx 설치됨, 미구현 |

---

## 8. 세션 3 추가 작업 (2026-03-17)

### 8.1 nvv4l2decoder 컨테이너 이슈 해결

**원인 확정**: `libgstnvvideo4linux2.so` 내부에서 `lsmod | grep nvgpu`를 실행해 디코더 경로를 결정함.
- `lsmod` 없음 → 검사 실패 → CUDA 경로(cuvidv4l2) 선택 → `libnvidia-encode.so` 부재 → EINVAL
- Jetson iGPU는 `libnvidia-encode.so` 미지원

**수정**: `docker/app/Dockerfile`에 `kmod` 패키지 추가

**검증**: 컨테이너 내 `NvMMLiteOpen: Block: BlockType=261` 출력 → HW 디코더 정상 초기화 확인

### 8.2 Phase 1 VLM 테스트 결과

`main.py`가 정상 구동 중 (IP 카메라 → MediaMTX → wally-backend-app):

| 검증 항목 | 결과 | 비고 |
|---|---|---|
| (1) 오류 없음 | **PASS** | 파이프라인 연속 구동, 에러 0 |
| (2) 추론 속도 500~1500ms | **CHECK** | 실측 평균 ~1700ms (기준 초과) |

- 추론 속도 1700ms: bench_vlm.py 기준 1000ms 예상보다 느림. CLIP→Transformers API 폴백 영향으로 추정
- 경고 `disabling CLIP with TensorRT due to limited memory` — TensorRT CLIP 빌드 없이 Transformers 폴백 사용 중

### 8.3 VLM 응답 파싱 수정

**증상**: `[WARN] 알 수 없는 행동 키: 'none of the above</s>'`
- VLM이 `DETECTED: none of the above` 형식으로 정상을 표현하는 경우 발생
- 동작에는 문제 없음 (None 반환 → 정상 처리)

**수정**: `main.py parse_vlm_response()`:
- `</s>` 등 EOS 토큰 제거 (`key.split("<")[0]`)
- `"none"` 포함 키는 WARN 없이 무시

### 8.4 미결 항목

| 항목 | 상태 | 비고 |
|---|---|---|
| 추론 속도 1700ms 원인 | 미결 | TensorRT CLIP 빌드 시 개선 가능성 있음 |
| OI-02 (TARGET_FPS, N_FRAMES) | 미결 | 실 반려동물 영상으로 측정 후 결정 |
| OI-03 (CONSEC_N) | 미결 | 오탐율 실험 후 결정 |
| FCM 알림 구현 | 미완 | `send_alert()` 로그 출력만 |
| VLM 정확도 검증 (Phase 2) | 미완 | 실 반려동물 행동 클립으로 7종 감지 정확도 측정 |

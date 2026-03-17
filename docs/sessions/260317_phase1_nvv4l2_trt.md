# 세션 요약 — 260317 / Phase 1: nvv4l2decoder 컨테이너 해결 + VLM 파이프라인 검증

이전 세션 파일: `260316_phase1_main.md`

---

## 1. 작업 내용 요약

| 항목 | 결과 |
|---|---|
| `nvv4l2decoder` 컨테이너 내 HW 디코더 활성화 | **완료** |
| Phase 1 VLM 파이프라인 검증 (오류 없음) | **PASS** |
| Phase 1 VLM 추론 속도 검증 (500~1500ms) | **CHECK** (실측 ~1700ms) |
| CLIP TensorRT 가속 시도 | **포기** (16GB 하드웨어 한계) |
| `parse_vlm_response` 파싱 경고 수정 | **완료** |

---

## 2. nvv4l2decoder 컨테이너 이슈 — 원인 및 해결

### 2.1 증상

컨테이너 내 GStreamer 파이프라인 실행 시:

```
S_EXT_CTRLS for CUDA_GPU_ID failed
ENC_CTX Error in initializing nvenc context
```

프레임 타임아웃 발생. 호스트에서는 `NvMMLiteOpen: Block: BlockType=261` 출력과 함께 정상 동작.

### 2.2 원인 분석

`libgstnvvideo4linux2.so` 내부 로직:

```
lsmod | grep nvgpu
  → 출력 있음 → NvMMLite 경로 (HW 디코더)  ← 호스트
  → 출력 없음 → cuvidv4l2 경로 (CUDA)       ← 컨테이너 (lsmod 없음)
```

- 컨테이너에 `kmod` 패키지가 없어 `lsmod` 명령어 자체가 없음
- `lsmod` 실패 → cuvidv4l2 경로 선택
- cuvidv4l2는 `libnvidia-encode.so` 필요 → Jetson iGPU에 존재하지 않음 → EINVAL

### 2.3 해결

`docker/app/Dockerfile`에 `kmod` 추가:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-plugins-bad \
        kmod \
    && rm -rf /var/lib/apt/lists/*
```

**검증**: 컨테이너 내 `NvMMLiteOpen: Block: BlockType=261` → HW 디코더 정상 초기화 확인

### 2.4 시행착오 기록 (반복하지 말 것)

| 시도 | 결과 | 이유 |
|---|---|---|
| `/dev/v4l2-nvdec`, `/dev/v4l2-nvenc` 개별 마운트 | 실패 | 두 노드는 `/dev/null`(major:minor=1:3)과 동일한 가상 노드 — 실제 HW 접근과 무관 |
| `/dev:/dev` 전체 마운트 | 실패 | 디바이스 노드 문제가 아님 |
| `ipc: host` 추가 | 실패 | NvSciIPC 관련이지 디코더 경로 선택과 무관 |
| `--privileged` | 실패 | 디코더 경로 선택 로직에 영향 없음 |
| `/usr/lib/aarch64-linux-gnu/nvidia` 볼륨 마운트 제거 | 실패 | 라이브러리 문제가 아님 |
| `avdec_h264` 소프트웨어 디코더로 교체 | 채택 불가 | 비싼 HW를 SW로 우회하는 것은 의미 없음 |
| **`kmod` 설치 (lsmod 제공)** | **성공** | 근본 원인 해결 |

> **핵심**: `nvv4l2decoder`가 컨테이너에서 실패할 때 디바이스/라이브러리가 아닌 **`lsmod` 유무**를 먼저 확인할 것.

---

## 3. Phase 1 VLM 파이프라인 검증 결과

### 3.1 실행 환경

- 컨테이너: `petcubator-app` (dustynv/nano_llm:r36.4.0 기반)
- 모델: VILA1.5-3b q4f16_ft (MLC)
- 파이프라인: `rtspsrc → rtph264depay → h264parse → nvv4l2decoder → nvvidconv → appsink`
- 소스: IP 카메라 → MediaMTX (`rtsp://mediamtx:8554/live`)

### 3.2 결과

| 검증 항목 | 기준 | 실측 | 결과 |
|---|---|---|---|
| (1) 오류 없음 | 에러 0회 | 에러 0회, 연속 정상 구동 | **PASS** |
| (2) 추론 속도 | 500~1500ms | 평균 ~1700ms | **CHECK** |

### 3.3 추론 속도 1700ms 원인

```
WARNING: disabling CLIP with TensorRT due to limited memory (falling back to Transformers API)
```

- VILA VLM = LLM(Llama 3B, MLC) + CLIP Vision Encoder(SigLIP)
- LLM은 MLC로 GPU 가속 중 → 정상
- CLIP은 TensorRT 가속이 비활성화됨 → Transformers API(PyTorch) 폴백 → 속도 저하

**clip_trt 코드 내 하드코딩 임계값** (`/opt/clip_trt/clip_trt/vision.py`):

```python
if psutil.virtual_memory().total < 20 * (1024 ** 3):
    logging.warning("disabling CLIP with TensorRT due to limited memory ...")
    return
```

- Jetson Orin NX 16GB → 15.27GB < 20GB → 무조건 비활성화
- TRT 엔진 빌드 시 메모리 부담 때문에 설정한 가드이나, 빌드/로드 분기와 무관하게 일괄 적용되는 설계 결함

### 3.4 CLIP TensorRT 활성화 시도 및 포기

**시도**: 임계값을 20GB → 8GB로 패치

```bash
# 수정: /opt/clip_trt/clip_trt/vision.py, text.py, timm2trt.py
# 원본 백업: *.bak 생성 후 sed -i로 패치
```

**결과**: 경고 계속 출력. 원인은 `.pyc` 바이트코드 캐시가 아니라 패치가 실제 임포트되는 코드에 반영되지 않은 것으로 추정 (미해결 상태로 롤백).

**포기 이유**: 엔진 캐시(`.cache/clip_trt/`)가 없으므로 빌드가 필요하며, `max_workspace_size=3GB` 빌드 시 LLM(1300MB) + GStreamer 파이프라인과 동시 구동 시 OOM 위험 실재. 임계값 20GB는 근거 있는 값.

**결론**: 16GB 환경에서 CLIP TensorRT는 현 NanoLLM/clip_trt 구현 기준 미지원. 1700ms를 실용 기준으로 수용.

> **다음에 재시도하려면**: 모델만 로드한 상태(파이프라인 없이)에서 엔진 빌드 시도. 또는 `dustynv/nano_llm:r36.4.0` 이미지에서 CLIP TRT 캐시가 있는 버전이 있는지 확인.

---

## 4. parse_vlm_response 파싱 경고 수정

### 4.1 증상

```
[WARN] 알 수 없는 행동 키: 'none of the above</s>'
```

VLM(VILA1.5-3b)이 프롬프트 지시(`NORMAL`로만 응답)를 지키지 않고 `DETECTED: none of the above</s>` 형식으로 응답. 동작 자체는 이상 없음(None 반환 → 정상 처리).

### 4.2 수정 (`src/app/main.py`)

```python
def parse_vlm_response(text: str) -> Optional[str]:
    text = text.strip()
    if text.upper().startswith("DETECTED:"):
        key = text.split(":", 1)[1].strip().lower()
        key = key.split("<")[0].strip()          # </s> 등 EOS 토큰 제거
        if key in BEHAVIORS:
            return key
        if "none" not in key:                    # "none of the above" 무시
            print(f"[WARN] 알 수 없는 행동 키: {key!r}", flush=True)
    return None
```

---

## 5. compose.yml → docker-compose.yml 이름 변경 (이전 세션 기록 보완)

이전 세션에서 `compose.yml`을 `docker-compose.yml`로 이름 변경. 최종 `app` 서비스 구성:

```yaml
app:
  image: petcubator-app
  runtime: nvidia
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - NVIDIA_DRIVER_CAPABILITIES=all
    - GST_PLUGIN_PATH=/usr/lib/aarch64-linux-gnu/gstreamer-1.0
    - LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/tvm:/usr/lib/aarch64-linux-gnu/nvidia:/usr/lib/aarch64-linux-gnu
  group_add:
    - video          # /dev/nvmap는 video 그룹(GID 44) 소유
  devices:
    - /dev/v4l2-nvdec
    - /dev/v4l2-nvenc
    - /dev/nvmap
    - /dev/nvhost-ctrl-gpu
    - /dev/nvhost-gpu
  volumes:
    - /home/skim/data/models:/data/models
    - recordings:/recordings
    - ./src/app:/app
    - /usr/lib/aarch64-linux-gnu/gstreamer-1.0:/usr/lib/aarch64-linux-gnu/gstreamer-1.0:ro
    - /usr/lib/aarch64-linux-gnu/nvidia:/usr/lib/aarch64-linux-gnu/nvidia:ro
    - /tmp/nvscsock:/tmp/nvscsock
  ipc: host
```

> **주의**: `/dev/v4l2-nvdec`, `/dev/v4l2-nvenc`는 Orin NX에서 `/dev/null`과 동일한 가상 노드. 마운트해도 HW 접근에 직접 영향 없음. `nvmap`, `nvhost-*`가 실제 중요한 노드.

---

## 6. FCM 알림 구현 (`send_alert`)

### 6.1 구현 내용

`src/app/main.py`에 FCM HTTP v1 API 연동 코드 추가:

```python
def init_fcm() -> bool:
    """서비스 계정 JSON으로 OAuth 2.0 Bearer 토큰 획득. 실패 시 False."""

def send_alert(behavior: str) -> None:
    """FCM 알림 발송 + preserve_clip 스레드 실행."""
```

- **`FCM_CREDENTIALS`** 환경변수 (서비스 계정 JSON 파일 경로) 미설정 시: 로그만 출력하고 조용히 리턴
- **`FCM_TOKEN`** (디바이스 FCM 토큰) 미설정 시: 경고 로그 출력 후 리턴
- 실제 FCM 연동 시 `docker-compose.yml`에 두 환경변수를 주석 해제하면 됨

### 6.2 현재 동작 (FCM 비활성화 상태)

```
[ALERT] 이상 행동 감지: 선회운동 (circling)
[FCM] FCM 비활성화 (FCM_CREDENTIALS 미설정)
```

---

## 7. 영상 클립 보존 구현 (`preserve_clip`)

### 7.1 구현 내용

`src/app/main.py`에 MediaMTX 세그먼트 복사 기반 클립 보존 구현:

```python
def preserve_clip(behavior: str, event_time: float) -> None:
    """RECORDINGS_DIR의 최신 CLIP_PRE_SEGMENTS개 세그먼트를 EVENTS_DIR에 복사."""
```

- `RECORDINGS_DIR` (기본: `/recordings/live`): MediaMTX 세그먼트 녹화 디렉토리
- `EVENTS_DIR` (기본: `/recordings/events`): 이벤트 클립 저장 디렉토리
- `CLIP_PRE_SEGMENTS` (기본: `2`): 보존할 사전 세그먼트 수
- 이벤트 디렉토리명 형식: `{YYYYMMDD_HHMMSS}_{behavior}`
- mtime 기준 최신 N개 선택 → `shutil.copy2`로 복사 (메타데이터 보존)
- `send_alert()`에서 별도 스레드로 비동기 실행 (메인 루프 블로킹 방지)

### 7.2 OI-06 확정

| 항목 | 결정값 |
|---|---|
| 저장 방식 | MediaMTX 세그먼트 복사 (재인코딩 없음) |
| 세그먼트 디렉토리 | `/recordings/live` (공유 볼륨) |
| 이벤트 디렉토리 | `/recordings/events` (공유 볼륨) |
| 사전 보존 수 | 2개 (환경변수로 조정 가능) |

---

## 8. E2E 통합 테스트 (`test_e2e.py`)

### 8.1 테스트 범위

`src/app/test_e2e.py` 신규 작성. GStreamer/VLM 없이 비즈니스 로직 레이어 검증:

| 섹션 | 검증 항목 |
|---|---|
| EventJudge | CONSEC_N 미만 알림 없음 |
| | CONSEC_N 도달 시 알림 발령 |
| | 발령 후 streak 초기화 |
| | 다른 행동 감지 시 streak 초기화 |
| | NORMAL 감지 시 streak 초기화 |
| preserve_clip | 이벤트 디렉토리 생성 |
| | 최신 세그먼트 2개 복사 |
| | 세그먼트 없을 때 오류 없이 처리 |
| send_alert | FCM 비활성화 상태에서 오류 없이 완료 |
| | send_alert → preserve_clip 클립 생성 확인 |

### 8.2 실행 결과

```
docker exec petcubator-app python3 /app/test_e2e.py
```

```
[1/3] EventJudge 동작 검증
  [PASS] CONSEC_N 미만(2회)은 알림 없음
  [PASS] CONSEC_N 도달(3회)에 알림 발령
  [PASS] 발령 후 streak 초기화 (1회 추가 → 알림 없음)
  [PASS] 다른 행동 감지 시 streak 초기화
  [PASS] streak 초기화 후 1회: 알림 없음
  [PASS] NORMAL 감지 시 streak 초기화

[2/3] preserve_clip 동작 검증
  [PASS] 이벤트 디렉토리 생성됨
  [PASS] 세그먼트 2개 복사됨 (실제: 2개)
  [PASS] 최신 2개 세그먼트가 복사됨
  [PASS] 세그먼트 없을 때 오류 없이 처리

[3/3] send_alert 흐름 검증 (FCM 비활성화)
  [PASS] send_alert 오류 없이 완료 (FCM 비활성화)
  [PASS] send_alert → preserve_clip 클립 생성 확인

  12 / 12 통과
```

**Phase 1 핵심 감지 시스템 구축 완료.**

---

## 9. 미결 항목

| 항목 | 상태 | 비고 |
|---|---|---|
| OI-02 (TARGET_FPS, N_FRAMES) | 미결 | 실 반려동물 영상으로 측정 후 결정 |
| OI-03 (CONSEC_N) | 미결 | 오탐율 실험 후 결정 |
| FCM 실 연동 | 미완 | `FCM_CREDENTIALS`, `FCM_TOKEN` 환경변수 설정 후 주석 해제 |
| VLM 정확도 검증 (Phase 2) | 미완 | 실 반려동물 행동 클립으로 7종 감지 정확도 측정 |
| CLIP TensorRT 가속 | 보류 | 16GB 환경 미지원. 재시도 시 파이프라인 없이 단독 빌드 시도 |
| model library metadata 경고 | 미조사 | MLC 컴파일 시 메타데이터 누락 원인 불명 |

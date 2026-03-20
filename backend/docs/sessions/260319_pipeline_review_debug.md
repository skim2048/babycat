# 260319 — 파이프라인 점검 및 디버그 대시보드

## 개요

Phase 0/1 완료 후 전체 파이프라인을 처음부터 재점검하고, 실시간 점검을 위한 디버그 대시보드를 구축한 세션.

## 파이프라인 점검

### 구조 재확인

MediaMTX에서 3갈래로 분기:

1. **Branch A** — WebRTC/HLS로 클라이언트에 직접 재배포 (실시간 스트리밍)
2. **세그먼트 녹화** — `/recordings/live/*.mp4` (60초 단위 순환 저장)
3. **Branch B** — wally-backend-app이 RTSP로 pull → GStreamer → VLM 추론

Branch B는 사실상 Branch A의 RTSP를 소비하는 내부 클라이언트.

### 미확인 가정 확인

| 항목 | 내용 | 결론 |
|---|---|---|
| H.264 코덱 | README 초기 작성 시 H.264로 가정, 명시적 논의 없었음 | 대부분의 IP 카메라가 H.264 지원. H.265 전환 시 파이프라인 2단어 수정으로 대응 가능. 기술부채 아닌 미확인 가정. → OI-09 추가 |
| ONVIF PTZ | 카메라 팬틸트 제어 요구 존재 (고객 요구) | 별도 ONVIF 세션으로 분리 개발 가능. PTZ 중 VLM 오탐 가능성은 UX 레벨에서 처리하는 방안 검토. → OI-10 추가 |
| 60초 청크 / CLIP_PRE_SEGMENTS=2 | 명확한 근거 없이 코드에 반영됨 | 실 환경에서 검증 필요 |

## 디버그 대시보드 구축

### 목적

파이프라인 4가지 점검 항목을 실시간으로 확인:
- 비디오 스트림이 흐르는가
- 해상도/프레임률이 납득할 수준인가
- VLM 추론 속도가 납득할만한가
- VLM 추론 결과가 납득할만한가

### 구현

`src/app/debug_server.py` — Python stdlib `http.server` 기반 (외부 의존성 없음)

- `GET /` — HTML 대시보드 (Light 테마)
- `GET /stream` — MJPEG 스트림 (VLM 입력 384x384 프레임)
- `GET /events` — SSE (추론 결과 + 하드웨어 상태 실시간)

대시보드 구성:
- 좌측: HLS 실시간 영상 (MediaMTX :8888 경유, hls.js)
- 우측 패널: Inference 프레임 + 추론 결과 + Pipeline 메트릭 + CPU/RAM/GPU 사용률 + 온도

### 기술 이슈

| 이슈 | 원인 | 해결 |
|---|---|---|
| FastAPI import 실패 | 베이스 이미지의 fastapi 0.99.0과 pydantic v2 충돌 | stdlib `http.server`로 전환 |
| WebRTC 연결 실패 | Docker 내부 ICE 후보가 컨테이너 IP 사용 | HLS로 대체 (TCP only, 안정적) |
| HLS 첫 로드 실패 | 세그먼트 미생성 시 hls.js 재시도 안 함 | fatal error 시 3초 후 자동 재시도 |
| `</s>` 토큰 노출 | NanoLLM generate()가 EOS 토큰을 문자열로 포함 | `.replace("</s>", "")` 필터링 |

## VLM 프롬프트 실험

### 실험 과정

| 프롬프트 | 결과 |
|---|---|
| 원본 (수의학 감시용, DETECTED/NORMAL 형식) | `DETECTED: None of the above</s>` — 지시를 따르지 못함 |
| `"What do you see in this image?"` | 번호 매겨 나열 (`1. The image shows...`) |
| `"What is the person or animal doing? Answer with one word only..."` | sitting, standing, walking만 출력. 예시 단어에 갇힘 |
| `"What is the person doing? Answer in one sentence."` | 가장 자연스럽고 구체적인 행동 묘사 |

### 결론

- VILA1.5-3b는 엄격한 출력 포맷 지시(DETECTED/NORMAL)를 잘 따르지 못함
- 제약을 줄이고 자유 서술시키면 더 나은 결과
- 프로덕션 프롬프트 설계 시 이 특성 반영 필요

## 멀티프레임 테스트 (N_FRAMES)

### N_FRAMES=1 → N_FRAMES=4 변경

| 항목 | 1프레임 | 4프레임 |
|---|---|---|
| 추론 시간 | ~1400ms | ~4200ms |
| 시간 축 정보 | 없음 | 제한적 |

### VILA1.5-3b의 temporal 처리 방식

- 전용 temporal encoder 없음
- 프레임 여러 장을 ChatHistory에 순서대로 넣는 multi-image 방식
- LLM이 텍스트 추론으로 프레임 간 차이를 유추 (진정한 temporal modeling 아님)

### 대안 모델 조사

Qwen2.5-VL-3B가 가장 현실적인 대안:
- mRoPE(Rotary Position Encoding)에 시간 차원 포함 — 인코딩 단계에서 temporal 처리
- 3B로 동일 크기, TensorRT-LLM 지원
- 단, NanoLLM 직접 통합 불가 — 별도 작업 필요

**합의**: 먼저 VILA1.5-3b + N_FRAMES=4로 실 반려동물 영상 테스트, 부족 시 Qwen2.5-VL-3B 전환 검토.

## 변경된 파일

| 파일 | 변경 |
|---|---|
| `src/app/debug_server.py` | 신규 — 디버그 대시보드 서버 |
| `src/app/main.py` | debug_state 연동, run_inference 반환값 변경, N_FRAMES 기본값 4 |
| `docker-compose.yml` | 포트 8080(디버그), 8888(HLS) 추가 |
| `config/mediamtx.yml` | `webrtcICEHostNAT1To1IPs` 추가 (WebRTC 시도 흔적) |

## 다음 단계

- 실 반려동물 영상으로 VLM 감지 능력 검증
- 프로덕션 프롬프트 설계 (수의학 감시용, 3B 모델 특성 반영)
- 부족 시 Qwen2.5-VL-3B 전환 검토
- API 서버 컨테이너 구현

# 260319 — ONVIF PTZ 검증 및 디버그 대시보드 개선

이전 세션 파일: `260319_pipeline_review_debug.md`

---

## 1. ONVIF PTZ 지원 검증

### 1.1 카메라 연결 정보

| 항목 | 값 |
|---|---|
| 카메라 IP | 192.168.1.101 |
| ONVIF 포트 | **2020** (80/443은 닫혀 있음) |
| ONVIF 엔드포인트 | `http://192.168.1.101:2020/onvif/service` |
| 인증 방식 | WS-Security PasswordDigest |
| 프로파일 토큰 | `profile_1` (mainStream, 1920×1080, H.264) |

### 1.2 PTZ 지원 항목

| 기능 | 지원 |
|---|---|
| AbsolutePanTilt (절대 위치 이동) | ✅ |
| RelativePanTilt (상대 이동) | ✅ |
| ContinuousPanTilt (속도 기반 연속 이동) | ✅ |
| Zoom (절대/상대/연속) | ❌ |
| HomeSupported | ❌ |
| Preset 저장 | ✅ (최대 8개) |
| Pan/Tilt 범위 | -1.0 ~ +1.0 (ONVIF 표준 정규화 좌표) |

**→ OI-10 (ONVIF PTZ 제어) 구현 가능 확인.**

---

## 2. 디버그 대시보드 개선

### 2.1 변경 사항

| 항목 | 변경 내용 |
|---|---|
| `추론 횟수`, `수신 프레임` 항목 | 제거 (디버깅 불필요 판단) |
| `소요 시간` 레이블 | `추론 당 소요 시간`으로 변경 |
| 섹션 구조 | 아코디언 방식으로 변경 (INFERENCE / PIPELINE / HARDWARE / PAN/TILT) |
| Hardware 섹션 | 온도(CPU/GPU Temp) 항목을 Hardware 섹션 내부로 통합 |

### 2.2 아코디언 구현

- `.section-title` 클릭 시 `.collapsed` 클래스 토글 → `.section-body { display: none }` 처리
- 화살표(▼) 아이콘 90도 회전으로 열림/닫힘 표시

---

## 3. PTZ 제어 기능 구현 (debug_server.py)

### 3.1 백엔드 (Python)

| 함수 | 역할 |
|---|---|
| `_onvif_auth_header()` | WS-Security PasswordDigest 헤더 생성 |
| `_onvif_post(body)` | SOAP 요청 (urllib.request, 외부 의존성 없음) |
| `ptz_move(pan, tilt)` | ContinuousMove — 버튼 누르는 동안 이동 |
| `ptz_stop()` | ContinuousMove 정지 |
| `ptz_absolute_move(pan, tilt)` | AbsoluteMove — 저장된 위치로 이동 |
| `ptz_get_status()` | GetStatus — 현재 Pan/Tilt 위치 조회 |
| `ptz_load_home()` | 시작 시 `/app/ptz_home.txt`에서 저장 위치 로드 |
| `ptz_save_home()` | 현재 폴링 위치를 `/app/ptz_home.txt`에 저장 |
| `_ptz_poll_loop()` | 백그라운드 스레드: 2초마다 GetStatus 폴링 |

**저장 파일 형식** (`/app/ptz_home.txt`, 호스트: `src/app/ptz_home.txt`):
```
pan=0.22
tilt=-0.553
```

### 3.2 HTTP 엔드포인트

`POST /ptz` — JSON body:

| action | 동작 |
|---|---|
| `move` + `pan`, `tilt` | ContinuousMove 시작 |
| `stop` | ContinuousMove 정지 |
| `save` | 현재 위치를 파일에 저장 |
| `goto` | 저장된 위치로 AbsoluteMove |

### 3.3 대시보드 PAN/TILT 섹션

- **현재 위치**: SSE로 2초마다 갱신되는 Pan/Tilt 값 표시
- **방향 버튼**: ▲▼◀▶ + ■(강제 정지)
  - mousedown → ContinuousMove 시작 (speed=0.5)
  - mouseup / mouseleave → Stop
  - touchstart / touchend 지원 (모바일)
- **저장/이동 버튼**:
  - `현재 저장`: 현재 폴링 위치를 파일에 저장
  - `저장 위치로`: AbsoluteMove로 저장된 좌표로 이동
- **저장된 위치**: SSE를 통해 파일 로드 직후부터 대시보드에 표시

### 3.4 DebugState 변경

- `frame_count`, `infer_count` 필드 제거 (SSE 스냅샷에서 제외)
- `snapshot()`에 `ptz_pan`, `ptz_tilt`, `ptz_saved_pan`, `ptz_saved_tilt` 추가

---

## 4. 신뢰도 표시 시도 → 철회

### 4.1 시도 내용

- INFERENCE_PROMPT에 `"End with CONFIDENCE:XX where XX is 0-100"` 추가
- `run_inference()` 반환값에 confidence 추가
- 대시보드 결과 레이블에 `(XX%)` 형식으로 표시

### 4.2 결과

VILA1.5-3b가 `CONFIDENCE:XX` 포맷 지시를 따르지 못하고 `'0'`만 출력. 이전 세션(260319)에서 확인된 **엄격한 포맷 지시 미준수** 특성의 재확인.

언어적 확신도 기반 휴리스틱(`_estimate_confidence()`) 도 시도했으나 빈 공장 촬영 중이라 검증 불가. 실 반려동물 영상이 준비될 때 재검토.

**→ 모든 관련 변경사항 롤백. 실 영상 확보 후 재논의.**

---

## 5. 변경된 파일

| 파일 | 변경 내용 |
|---|---|
| `src/app/debug_server.py` | ONVIF PTZ 함수 추가, `POST /ptz` 엔드포인트, 대시보드 개선 (아코디언, PTZ 섹션) |
| `src/app/main.py` | `frame_count`, `infer_count` 제거 반영, `update_inference()` 시그니처 정리 |
| `src/app/ptz_home.txt` | 신규 — PTZ 저장 위치 파일 (pan=0.22, tilt=-0.553) |

---

## 6. 미결 항목

| 항목 | 상태 | 비고 |
|---|---|---|
| OI-02 (TARGET_FPS, N_FRAMES) | 미결 | 실 반려동물 영상으로 측정 후 결정 |
| OI-03 (CONSEC_N) | 미결 | 오탐율 실험 후 결정 |
| OI-10 (ONVIF PTZ) | **구현 완료** | PTZ 기능 동작 확인. PTZ 중 VLM 오탐 방지 로직은 추후 결정 |
| 프로덕션 프롬프트 설계 | 미완 | 실 반려동물 영상 필요 |
| VLM 신뢰도 표시 | 보류 | 실 영상 확보 후 재검토 |
| API 서버 컨테이너 구현 | 미완 | Phase 3 범위 |

---

## 7. 다음 단계

- 실 반려동물 영상으로 VLM 감지 능력 검증
- 프로덕션 프롬프트 설계 (수의학 감시용, 3B 모델 특성 반영)
- 부족 시 Qwen2.5-VL-3B 전환 검토
- API 서버 컨테이너 구현

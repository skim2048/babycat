# AI Camera Event Detection

> **목적**: RTSP 카메라 영상을 실시간으로 분석하여 사용자가 정의한 조건이 감지되면 푸시 알림을 전송하는 엣지 AI 시스템.
> **버전**: v1.5

| 버전 | 변경 내용 |
|---|---|
| v0.1 | 최초 작성 |
| v0.2 | 파이프라인 아키텍처 초안 (Tee 분리 모델, Ring Buffer, 실시간 스트리밍, Docker 컨테이너 구성) |
| v0.3 | 프로젝트명 확정 |
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

**클립 저장**: 이상 감지 시 MediaMTX 세그먼트를 이벤트 폴더로 보존 (pre-event 포함).

### 4.3 설계 원칙

- 엣지 완결형 — Jetson 단독 처리, 외부 추론 서버 없음
- GPU 디코딩(nvv4l2decoder) 기본 사용
- 감지 조건은 코드 외부(설정)에서 주입 — VLM 모델 및 프롬프트 교체 가능

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
- [ ] 감지 조건 외부화 — 사용자 정의 조건을 설정 파일/UI로 주입
- [ ] 클라이언트 앱 (Android) — 실시간 스트리밍, 이벤트 이력, 알림 수신
- [ ] API 서버 구현 (기기 토큰, 이벤트 이력, 클립 제공)

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

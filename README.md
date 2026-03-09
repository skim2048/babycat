# Petcubator — Project Initiation Document

> **목적**: 이 문서는 Claude Code와의 협업을 위한 프로젝트 시작 기준 문서입니다.  
> 미결 사항(Open Issues)이 다수 존재하며, 설계 진행 중 이 문서를 지속 갱신합니다.  
> **버전**: v0.4 (Draft)

| 버전 | 변경 내용 |
|---|---|
| v0.1 | 최초 작성 |
| v0.2 | 파이프라인 아키텍처 초안 추가 (Tee 분리 모델, Ring Buffer, 실시간 스트리밍 뷰, Docker 컨테이너 운영 방식) — 미확정, Claude Code와의 협의 대상 |
| v0.3 | 프로젝트명 Petcubator로 확정 |
| v0.4 | 4.2 파이프라인 다이어그램을 Mermaid 문법으로 교체 |

---

## 1. 프로젝트 목적

반려견이 펫하우스 내부에 혼자 있는 동안 발생할 수 있는 이상 행동을 **24시간 실시간으로 감지**하여 견주에게 즉시 알림을 전달한다. 견주는 앱에서 펫하우스 영상을 실시간으로 확인할 수도 있다.

- 촬영 대상: 단일 반려견, 펫하우스 내부 고정 카메라
- 감지 방식: 영상 기반 VLM 추론 (청각 감지는 Phase 2로 유보)
- 알림 수단: 웹앱 또는 Android 앱 푸시 알림
- 부가 기능: 앱에서 실시간 영상 스트리밍 뷰 제공

---

## 2. 하드웨어 구성

| 구성 요소 | 사양 | 비고 |
|---|---|---|
| Edge AI 보드 | NVIDIA Jetson Orin NX 16GB | GPU+CPU 통합 메모리 16GB |
| 카메라 | IR 지원 IP Camera | RTSP 스트림, 야간 촬영 가능 |
| 네트워크 | 유선 이더넷 권장 | Wi-Fi는 스트림 지연 위험 |
| 스토리지 | NVMe SSD 권장 | 모델 로딩 속도 고려 |

**제약사항**:
- Jetson Orin NX 16GB는 CPU/GPU 통합 메모리 구조 — VLM 모델 크기가 전체 메모리 가용량에 직접 영향
- 외부 클라우드 추론 서버 없음 — Jetson 단독 처리 (엣지 완결형)

---

## 3. 감지 대상 행동

### Phase 1 (시각 기반, 현재 범위)

| # | 행동 | 판별 방식 | 임상적 관련성 |
|---|---|---|---|
| 1 | 발작 (Seizure) | 시각 | 뇌전증, 독성 물질 노출 |
| 2 | 구토 (Vomiting) | 시각 | 소화기 장애, 독소 섭취 |
| 3 | 헛구역질 (Retching) | 시각 | 위 염전(GDV) 전조 |
| 4 | 긁기 (Scratching) | 시각 | 피부 질환, 기생충, 알레르기 |
| 5 | 선회운동 (Circling) | 시각 | 전정 장애, 뇌 병변 |
| 6 | 핥기 과다 (Excessive Licking) | 시각 | 통증 부위, 피부 자극 |
| 7 | 헐떡임 과다 (Excessive Panting) | 시각 | 열사병, 통증, 불안 |

### Phase 2 (청각 추가 후 감지 가능)

| # | 행동 | 이유 |
|---|---|---|
| 8 | 기침 (Coughing) | 시각만으로 판별 난이도 높음 |
| 9 | 짖음 (Barking) | 청각 단서 필수 |
| 10 | 하울링 (Howling) | 청각 단서 필수 |

---

## 4. 시스템 아키텍처

### 4.1 컨테이너 구성 (운영 방식)

Jetson 내부의 서비스들은 Docker 컨테이너로 분리하여 운용한다.

| 컨테이너 | 역할 | 비고 |
|---|---|---|
| NanoLLM 컨테이너 | VLM 추론 (VILA 등) | Jetson Containers 기반 |
| MediaMTX 컨테이너 | RTSP/WebRTC 스트리밍 서버 | Branch A 스트림 수신 및 재배포 |
| App 컨테이너 | GStreamer 파이프라인, 이벤트 판정, FCM 발송 | Python 애플리케이션 |

### 4.2 파이프라인 아키텍처 초안

> **⚠️ 미확정**: 아래 구조는 Claude Code와의 협의를 통해 검토 및 변경될 수 있다.  
> 핵심 문제 의식: 실시간 스트리밍과 VLM 추론이 동일 파이프라인에서 직렬로 처리될 경우, 추론 지연(수 초)이 스트리밍 FPS를 블로킹한다. 이를 방지하기 위해 GStreamer `tee`를 통한 비동기 분리 구조를 초안으로 검토 중이다.

``` mermaid
flowchart TD
    CAM["IP Camera\n(IR 지원, RTSP)"]

    subgraph JETSON["Jetson Orin NX 16GB"]

        subgraph APP["App 컨테이너"]
            subgraph GST["GStreamer Pipeline"]
                SRC["rtspsrc\n(RTSP 수신)"]
                DEC["nvv4l2decoder\n(GPU 하드웨어 디코딩)"]
                TEE["tee\n(스트림 분기)"]

                subgraph BRANCH_A["Branch A — 실시간 스트리밍 (독립 스레드)"]
                    QA["queue"]
                    ENC["NVENC\n(하드웨어 인코더)"]
                end

                subgraph BRANCH_B["Branch B — AI 분석 (독립 스레드)"]
                    QB["queue\n(drop=true, max-buffers 제한)"]
                    VRATE["videorate\n(FPS 제한)"]
                    CONV["nvvideoconvert\n(포맷 변환)"]
                    SINK["appsink"]
                end
            end

            subgraph PYAPP["Python Application"]
                RING["Ring Buffer\n(최근 N초 순환 저장\n※ 약 6.22MB/frame @ 1080p RGB)"]
                INFER["추론 요청\n(비동기)"]
                JUDGE["이벤트 판정\n(연속 감지 조건)"]
            end
        end

        subgraph NANOLLM["NanoLLM 컨테이너"]
            VLM["VLM 추론\n(VILA 등)"]
        end

        subgraph MEDIAMTX["MediaMTX 컨테이너"]
            MTX["RTSP/WebRTC\n스트리밍 서버"]
        end
    end

    subgraph FCM_CLOUD["Firebase Cloud Messaging"]
        FCM["FCM\n(HTTP v1 API)"]
    end

    subgraph CLIENT["클라이언트"]
        WEB["웹앱"]
        APP_MOB["Android 앱"]
    end

    STORAGE["MP4 클립\n(로컬 스토리지)"]

    %% 메인 흐름
    CAM -->|"RTSP Stream (H.264/H.265)"| SRC
    SRC --> DEC --> TEE

    %% Branch A
    TEE -->|Branch A| QA --> ENC --> MTX
    MTX -->|"실시간 스트림"| WEB
    MTX -->|"실시간 스트림"| APP_MOB

    %% Branch B
    TEE -->|Branch B| QB --> VRATE --> CONV --> SINK
    SINK -->|"프레임 Push"| RING
    SINK -->|"프레임 추출 (비동기)"| INFER
    INFER -->|"추론 요청"| VLM
    VLM -->|"감지 결과"| JUDGE

    %% 이벤트 처리
    JUDGE -->|"이상 감지"| RING
    RING -->|"사전 프레임 병합"| STORAGE
    JUDGE -->|"알림 발송"| FCM
    FCM --> WEB
    FCM --> APP_MOB
```

**Branch A — 실시간 스트리밍**:
- 독립 스레드에서 동작하여 Branch B의 추론 지연과 완전히 격리
- NVENC(하드웨어 인코더) → MediaMTX를 통해 앱에 RTSP/WebRTC 스트림 제공

**Branch B — AI 분석**:
- `videorate`로 추론 주기에 맞게 FPS 제한 → 불필요한 추론 비용 제거
- `appsink`의 `drop=true`, `max-buffers` 제한으로 파이프라인 블로킹 방지
- Ring Buffer: 최근 N초 프레임을 메모리에 순환 보관 (1080p RGB 기준 약 6.22MB/frame)
- 이상 감지 시 Ring Buffer(사전) + 이후 프레임을 병합하여 MP4로 저장

### 4.3 설계 원칙

- 외부 클라우드 추론 서버 없음 — Jetson 단독 처리 (엣지 완결형)
- GPU 디코딩(nvv4l2decoder) 및 TensorRT 최적화 추론을 기본으로 가정
- VLM 모델 교체를 고려하여 추론 인터페이스는 추상화 레이어로 분리
- 16GB 통합 메모리 내에서 Ring Buffer 크기, 모델 크기, 영상 파이프라인 메모리가 경합 — OOM 방지를 위한 메모리 예산 설계 필요

---

## 5. 소프트웨어 스택 후보

### 5.1 VLM 추론 환경

> **미결 (OI-01)**: Phase 0에서 메모리 및 추론 속도 벤치마크 후 결정.

| 후보 | 근거 | 우선순위 |
|---|---|---|
| NanoLLM + VILA | Jetson 공식 지원, Jetson Containers 제공, 설정 단순 | 1순위 (우선 검토) |
| TensorRT-LLM | 최고 추론 성능, NVIDIA 공식 지원 | 2순위 (성능 미달 시) |
| Ollama (멀티모달) | 배포 용이, 범용성 높음 | 3순위 (Jetson 최적화 미흡) |

참고:
- Jetson Containers: https://github.com/dusty-nv/jetson-containers
- NanoLLM: https://github.com/dusty-nv/NanoLLM
- VILA: https://github.com/NVlabs/VILA

### 5.2 영상 파이프라인

- **GStreamer** + **nvv4l2decoder**: RTSP 수신 및 GPU 하드웨어 가속 디코딩 (기본)
- **NVENC**: Branch A 하드웨어 인코딩
- **MediaMTX**: RTSP/WebRTC 스트리밍 서버 (컨테이너로 운용)
- **OpenCV VideoWriter**: 이상 감지 시 MP4 클립 저장
- **DeepStream SDK**: 파이프라인 관리 복잡도 증가 위험 — 필요 시 검토

### 5.3 알림 인프라

- **FCM HTTP v1 API**: Jetson에서 직접 호출, 별도 서버 불필요
- 인증: 서비스 계정 기반 OAuth 2.0
- 대상: 웹앱(PWA 또는 브라우저 푸시) 및 Android 앱 공통 경로
- 참고: https://firebase.google.com/docs/cloud-messaging/migrate-v1

---

## 6. 주요 기술 리스크

| 리스크 | 내용 | 대응 방향 |
|---|---|---|
| 메모리 부족 (OOM) | VLM + Ring Buffer + 영상 파이프라인이 16GB 통합 메모리를 경합 | 컴포넌트별 메모리 예산 사전 설계, 모델 양자화(INT4/INT8) |
| Ring Buffer 크기 | 1080p RGB 기준 1프레임 약 6.22MB — N초 버퍼가 메모리에 직접 영향 | 해상도·FPS·버퍼 시간 트레이드오프 결정 필요 |
| 추론 지연 | VLM 추론 수 초 소요 — Branch B FPS와 감지 반응성에 영향 | TensorRT 최적화, 샘플링 주기 조정 |
| 파이프라인 블로킹 | appsink 처리 지연 시 GStreamer 파이프라인 정지 위험 | drop=true, max-buffers 제한으로 오래된 프레임 강제 폐기 |
| VLM 오탐율 | 유사 행동 혼동 (정상 핥기 vs. 과다 핥기 등) | 연속 감지 조건, 신뢰도 임계값 튜닝 |
| 모델 미확정 | VILA 외 대안 평가 미완료 | 추론 인터페이스 추상화로 교체 비용 최소화 |
| 야간 화질 | IR 영상에서 VLM 정확도 저하 가능성 | IR 영상 기반 별도 검증 필요 |

---

## 7. 미결 사항 (Open Issues)

Claude Code와 함께 아래 항목들을 순서대로 결정한다.

| # | 항목 | 결정에 필요한 작업 |
|---|---|---|
| OI-01 | VLM 모델 최종 선정 | Jetson에서 후보 모델별 메모리/추론속도 벤치마크 |
| OI-02 | 프레임 샘플링 주기 (Branch B FPS) | 추론 지연과 감지 반응성 간 트레이드오프 측정 |
| OI-03 | 연속 감지 조건 기준값 (N회, T초) | 오탐율과 반응속도 간 균형점 실험 |
| OI-04 | Ring Buffer 크기 (N초) | 메모리 예산, 클립 저장 요건과 연동하여 결정 |
| OI-05 | Tee 분리 파이프라인 구조 채택 여부 | Claude Code와 대안 설계 검토 후 결정 |
| OI-06 | 이벤트 영상 클립 저장 구현 방식 | Ring Buffer 크기, 스토리지 용량 계획과 연동 |
| OI-07 | 웹앱 vs Android 앱 우선순위 | FCM 연동은 공통이나 개발 공수 판단 필요 |
| OI-08 | 컨테이너 간 통신 방식 | NanoLLM ↔ App 컨테이너 간 추론 요청/응답 인터페이스 설계 |

---

## 8. 단계별 실행 계획

### Phase 0 — 환경 구성 및 파이프라인 설계 검증
- [ ] Docker 컨테이너 구성 (NanoLLM, MediaMTX, App)
- [ ] NanoLLM + VILA 동작 확인
- [ ] RTSP 수신 및 GPU 디코딩 검증
- [ ] 후보 모델 메모리/속도 벤치마크 → **OI-01 결정**
- [ ] Tee 분리 파이프라인 구조 검토 → **OI-05 결정**
- [ ] 컨테이너 간 통신 방식 설계 → **OI-08 결정**
- [ ] Branch B FPS 및 Ring Buffer 크기 실험 → **OI-02, OI-04 결정**

### Phase 1 — 핵심 감지 시스템 구축
- [ ] GStreamer 파이프라인 구현 (확정된 구조 기반)
- [ ] VLM 프롬프트 설계 (7종 행동 분류)
- [ ] 이벤트 판정 로직 구현 → **OI-03 결정**
- [ ] FCM 연동 및 알림 발송 구현
- [ ] 영상 클립 저장 구현 → **OI-06 결정**
- [ ] 종단 통합 테스트

### Phase 2 — 청각 감지 추가 및 정확도 개선
- [ ] 마이크 입력 통합
- [ ] 기침·짖음·하울링 감지 추가
- [ ] 오탐율 개선

### Phase 3 — 앱 완성
- [ ] 웹앱 또는 Android 앱 개발 → **OI-07 결정**
- [ ] 실시간 스트리밍 뷰 (Branch A 연동)
- [ ] 이벤트 이력 및 영상 클립 조회 기능

---

## 9. 용어 정의

| 용어 | 정의 |
|---|---|
| 엣지 완결형 | 외부 서버 없이 Jetson 단독으로 감지~알림 전 처리를 수행하는 구조 |
| 연속 감지 조건 | 단발성 오탐을 방지하기 위해 N회 연속 또는 T초 내 M회 감지 시에만 알림을 발송하는 조건 |
| 통합 메모리 | Jetson Orin NX의 CPU와 GPU가 물리적으로 동일한 메모리 풀을 공유하는 구조 |
| Tee | GStreamer 플러그인. 단일 입력 스트림을 복수의 독립 Branch로 분기 |
| Ring Buffer | 최근 N초 분량의 프레임을 순환 구조로 메모리에 유지하는 버퍼. 이상 감지 시 사전 영상 보존에 사용 |
| Branch A | Tee에서 분기된 실시간 스트리밍 경로. MediaMTX를 통해 앱에 영상 제공 |
| Branch B | Tee에서 분기된 AI 분석 경로. FPS 제한 후 appsink로 Python에 전달 |
| appsink | GStreamer 파이프라인에서 Python 애플리케이션 메모리로 프레임을 전달하는 싱크 엘리먼트 |
| MediaMTX | RTSP/WebRTC 스트리밍 서버. 컨테이너로 운용 |
| VLM | Visual Language Model. 이미지와 텍스트를 함께 처리하는 멀티모달 언어 모델 |
| RTSP | Real Time Streaming Protocol. IP 카메라의 영상 스트림 전송 표준 프로토콜 |
| FCM | Firebase Cloud Messaging. Google의 크로스 플랫폼 푸시 알림 인프라 |
| OOM | Out-Of-Memory. 메모리 초과로 인한 프로세스 강제 종료 상태 |

---

*이 문서는 설계 진행에 따라 지속 갱신됩니다. 미결 사항이 결정되면 해당 섹션을 업데이트하고 이력을 기록하십시오.*
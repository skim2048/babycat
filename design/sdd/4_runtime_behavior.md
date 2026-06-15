# 4. Runtime Behavior; 런타임 동작

Section 3에서 다루는 정적 연결이 아니라, 실행 중 발생하는 동적 흐름을 기술한다. Babycat 설계의 핵심 복잡도는 대부분 이 영역에 존재한다.

## 4.1 Pipeline Lifecycle; 파이프라인 수명주기
GStreamer 파이프라인의 시작·재시작·정지. (작성 예정)
근거: `app/main.py` (`start_pipeline`, `restart_pipeline`), `app/pipeline_lifecycle.py`

## 4.2 Inference and Event Detection; 추론·이벤트 감지
프레임 추출 → VLM 추론 → 키워드 매칭. (작성 예정)
근거: `app/main.py` (`inference_worker`, `RingBuffer`), `app/vlm_worker.py`

## 4.3 Trigger Clip Recording; 트리거 클립 녹화
이벤트 감지 시 클립 저장. 직접 RTSP 재녹화 / 롤오버 세그먼트 두 경로. (작성 예정)
근거: `app/main.py` (`save_trigger_clip`), `app/trigger_clip_rollover.py`

## 4.4 Failure Recovery; 장애 복구
워치독에 의한 파이프라인 자동 복구. (작성 예정)
근거: `app/main.py` (`watchdog_worker`)

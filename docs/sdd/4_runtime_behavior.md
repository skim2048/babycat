# 4. Runtime Behavior; 런타임 동작

Section 3의 정적 연결이 아니라, 실행 중 발생하는 동적 흐름을 기술한다. Babycat 설계의 핵심 복잡도는 대부분 이 영역, 곧 ***App Server*** 내부에 있다.

## 4.1 Pipeline Lifecycle; 파이프라인 수명주기

***App Server***는 ***MediaMTX Server***의 스트림을 GStreamer 파이프라인으로 받아 프레임을 추출한다.

`rtspsrc(TCP) → rtph264depay → h264parse → nvv4l2decoder → nvvidconv(RGBA) → videorate → appsink`

- **하드웨어 디코딩** — `nvv4l2decoder`·`nvvidconv`는 Jetson NVDEC를 사용한다.
- **프레임율 정규화** — `videorate`가 소스의 원본 FPS와 무관하게 `TARGET_FPS`(기본 1fps)로 균일화한다. 추론은 초당 한 장으로 충분하므로 30/60fps 소스도 그 비율로 솎아 낸다.
- **최신 프레임 우선** — `appsink`는 `drop=true, max-buffers=1`로, 추론이 밀리면 오래된 프레임을 버리고 항상 최신 프레임만 남긴다.

**지연 기동** — 파이프라인은 두 전제가 갖춰져야 시작한다: (1) VLM 모델 로드 완료, (2) 카메라 프로필 적용. 하나라도 미비하면 `PipelineLifecycle`이 대기 상태(`waiting_for_vlm`/`waiting_for_camera`)로 보류하다가, 충족되면 한 번 시작한다. 기동 순서는 ① HTTP 서버(8080) 기동 → ② 저장된 프로필 적용(백그라운드) → ③ VLM 사전 컴파일·로드 → ④ 추론·워치독 스레드 기동 → ⑤ 파이프라인 시작이다.

근거: `app/main.py`(`build_pipeline_str`, `start_pipeline`, `restart_pipeline`, `main`), `app/pipeline_lifecycle.py`

## 4.2 Inference and Event Detection; 추론·이벤트 감지

프레임 추출과 추론은 **서로 다른 스레드**에서 비동기로 동작하며, `RingBuffer`와 단일 슬롯 큐로 연결된다.

- **프레임 콜백(GStreamer 스레드)** — appsink의 RGBA 버퍼를 384×384 RGB로 변환해 `RingBuffer`(크기 `RING_SIZE`=30)에 넣고 추론 큐에 신호를 보낸다. 큐가 차 있으면(이전 추론 진행 중) 신호를 버린다 — 자연스러운 백프레셔.
- **추론 스레드** — 신호를 받으면 링버퍼에서 최신 `N_FRAMES`(기본 4)장을 꺼내 VLM 추론을 수행한다. PTZ가 움직이는 중이면 건너뛴다(흔들린 화면 추론 회피).
- **키워드 매칭** — 추론 텍스트(소문자)에 사용자가 설정한 키워드(`triggers`)가 부분 문자열로 포함되면 **이벤트**로 판정한다.
- **이벤트 처리** — 이벤트 시 별도 스레드로 `save_trigger_clip`을 띄운다(§4.3). 추론 결과는 매 회 `app_state`에 게시되어 모니터링 피드(SSE)로 노출된다.

**VLM 격리** — VLM 모델은 ***App Server*** 본체가 아니라 **자식 프로세스**(`VlmProcess`)에서 실행된다. 모델 교체 시 자식을 종료해 이전 모델의 CUDA/TVM/TensorRT 메모리를 OS가 회수하게 하려는 설계다. 교체 요청은 추론과 추론 *사이*에서만 처리되어 생성 도중에 끊기지 않는다.

근거: `app/main.py`(`RingBuffer`, `make_frame_callback`, `inference_worker`, `ModelHolder`, `_perform_switch`), `app/vlm_worker.py`

## 4.3 Trigger Clip Recording; 트리거 클립 녹화

이벤트 감지 시 그 시점 전후의 영상을 클립으로 저장한다. 같은 이벤트의 반복 저장은 `TRIGGER_COOLDOWN`(30초) 안에서 무시된다. 녹화에는 두 경로가 있다.

- **직접 RTSP 녹화(기본)** — ffmpeg가 ***MediaMTX Server***에서 RTSP(TCP)로 `TRIGGER_CLIP_DUR`(5초)을 받아 코덱 복사로 저장한다. 단순하나 **이벤트 시점부터 *앞으로*만** 녹화하므로 사전 영상이 없다.
- **롤오버 세그먼트 녹화(선택, `TRIGGER_ROLLOVER_ENABLED`)** — 별도 워커가 ***MediaMTX Server***에서 1초 단위 `.ts` 세그먼트를 연속 녹화해 짧은 보존창(`TRIGGER_SEGMENT_RETENTION`=15초)으로 유지한다. 이벤트 시 `[event-PRE(2초), event+POST(5초)]` 구간의 세그먼트를 골라 ffmpeg concat(복사)으로 잇는다. 이로써 **사전 영상까지** 포함된다. 실패하면 직접 녹화로 폴백한다.

**용량 관리** — 저장 전 `ensure_clip_capacity`가 여유 공간을 확인하고(`min 256MB`/`target 512MB`), 부족하면 오래된 클립을 최대 20개까지 정리한다. 그래도 부족하면 해당 클립 저장을 건너뛴다.

**산출물** — `{DATA_DIR}/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4`와 동명의 `.json` 메타데이터(§5.2).

근거: `app/main.py`(`save_trigger_clip`, `_record_direct_trigger_clip`, `_finalize_rollover_clip`, `_segment_recorder_worker`), `app/trigger_clip_rollover.py`, `app/clip_storage.py`

## 4.4 Failure Recovery; 장애 복구

- **파이프라인 워치독** — 5초마다 점검하여, PLAYING 후 유예(15초)가 지났는데도 프레임이 일정 시간(15초) 들어오지 않으면 파이프라인을 재시작한다. `rtspsrc`가 ***MediaMTX Server*** 준비 전에 접속했다가 멎는 상황을 자동 복구한다.
- **VLM 자식** — 추론 중 자식이 죽으면 `VlmProcess`가 스스로 재기동한다. 한 회 실패는 건너뛰고 다음 프레임으로 진행한다.
- **세그먼트 워커** — ffmpeg가 죽거나 시동 후 세그먼트를 만들지 못하면 지수 백오프로 재시작한다.
- **모델 교체** — 교체 실패 시 이전 모델로 롤백을 시도한다.

근거: `app/main.py`(`watchdog_worker`), `app/pipeline_lifecycle.py`, `app/vlm_worker.py`

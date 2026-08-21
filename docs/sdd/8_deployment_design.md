# 8. 배포 설계 (Deployment Design)

## 8.1 컨테이너 구성 (Container Composition)

네 서비스 모두 재시작 정책은 `unless-stopped`다(`NFR-018`).

|서비스|베이스|하드웨어 접근|볼륨|포트 공개|
|---|---|---|---|---|
|`router`|python slim + FastAPI|없음|`data/db/router`|8000/tcp|
|`streamer`|python slim + MediaMTX 정적 바이너리(다단계 복사) + FastAPI|없음|`config`|8189/udp|
|`analyzer`|NanoLLM(jetson-containers)|NVDEC·GPU 장치, 호스트 GStreamer 플러그인·tegra 라이브러리(ro), NvSciIPC 소켓, host IPC|`data/models`·`data/state/analyzer`|없음|
|`recorder`|ubuntu 계열 + GStreamer + FastAPI + ffmpeg|NVDEC·NVENC 장치, 호스트 GStreamer 플러그인·tegra 라이브러리(ro), NvSciIPC 소켓, host IPC|`data/clips`·`data/db/recorder`·`data/state/recorder`, tmpfs(`/run/babycat-segments`)|없음|

`analyzer`와 `recorder`의 하드웨어 접근 항목이 같은 것은 우연이 아니다 — 둘 다 `nvv4l2decoder` 경로를 쓰며, `recorder`는 `nvv4l2h264enc`를 위해 NVENC 장치가 더해진다(§2.4 (3)). 데이터 볼륨은 §5.3의 소유 구획대로 서비스별로 좁혀 마운트하여, 소유하지 않은 데이터가 컨테이너 안에서 보이지 않게 한다.

## 8.2 이미지 빌드 (Image Build)

- 현장 빌드를 전제한다(SRS §3.3). `router`와 `streamer`는 같은 python slim 베이스를 공유하여 레이어 중복을 줄인다. `streamer` 이미지는 공식 MediaMTX 이미지에서 정적 바이너리를 다단계 복사(`COPY --from`)로 가져와 담으며, 버전 인상은 참조 태그의 변경이다.
- `analyzer`의 베이스(NanoLLM)는 크기가 지배적이므로, 소스 변경이 베이스 레이어를 무효화하지 않도록 의존 설치와 소스 복사를 레이어로 분리한다. 개발 중에는 소스를 볼륨으로 마운트하여 재빌드 없이 반영한다.
- VLM 모델의 사전 컴파일(SRS §3.2)은 이미지 빌드가 아니라 최초 기동의 런타임에 일어나며, 결과는 `data/models`에 캐시되어 재기동·재빌드와 무관하게 재사용된다. 이 분리 덕에 이미지 재빌드가 수십 분의 재컴파일을 유발하지 않는다.

## 8.3 설정 주입 (Configuration Injection)

주입 값은 `.env` 파일과 Compose의 환경 변수로 전달한다. 비밀키와 자격증명은 형상 관리에서 제외하며(SRS §3.6), 저장소에는 `.env.example` 템플릿만 둔다.

|변수|대상|필수|설명|
|---|---|---|---|
|`HOST_IP`|`streamer`|필수|WebRTC ICE 후보로 광고할 외부 도달 가능 IP|
|`JWT_SECRET`|`router`|필수|토큰 서명 비밀키(`NFR-013`). 기본값 사용 금지|
|`JWT_EXPIRY`·`REFRESH_EXPIRY`|`router`|선택|토큰 수명. 기본값은 SRS `FR-001`·`FR-002`의 600초·30일|
|`DEFAULT_USER`·`DEFAULT_PASS`|`router`|필수|최초 기동 시 1회 생성되는 초기 계정(SRS §3.2)|
|`VLM_MODELS`|`analyzer`|필수|후보 VLM 모델 목록(SRS §3.2)|
|`MAX_NEW_TOKENS`|`analyzer`|선택|생성 토큰 상한(§7.2)|
|`MIN_INFER_INTERVAL`|`analyzer`|선택|추론 시작 간격의 하한(초, SRS `FR-058`). 기본 0(자연 주기)|
|`INFERENCE_RETENTION_DAYS`|`recorder`|선택|추론 이력 보존 기간(SRS `FR-053`). 기본 90일|
|`TZ`|전체|선택|컨테이너 로컬 시간대. 날짜 필터의 달력 기준(기본 Asia/Seoul)|
|`CORS_EXTRA_ORIGINS`|`router`|선택|사설망 허용 규칙 밖에서 추가로 허용할 origin 목록|
|`TRIGGER_COOLDOWN`|`recorder`|선택|이벤트 묶음 처리 간격(SRS `FR-030`)|
|`TRIGGER_CLIP_DUR`·`TRIGGER_PRE_EVENT_SEC`·`TRIGGER_POST_EVENT_SEC`|`recorder`|선택|클립 창(§7.2). 사후 구간은 미설정 시 기본 길이를 따름|
|`CLIP_MIN_FREE_MB`·`CLIP_TARGET_FREE_MB`|`recorder`|선택|자동 정리 발동·회복 여유 수위(SRS `FR-033`)|
|`RECORDER_ENCODE_BITRATE`·`RECORDER_ENCODE_FPS`|`recorder`|선택|세그먼트 재인코딩 비트레이트와 소스 프레임레이트 가정(§4.4)|

## 8.4 로그와 진단 (Logging and Diagnostics)

- 모든 서비스는 로그를 표준 출력으로 내보내고, 수집·보존은 컨테이너 런타임의 로그 드라이버(로테이션 설정 포함)에 맡긴다. 별도의 로그 수집 컴포넌트를 두지 않는다 — 단일 호스트·소수 운영자 전제에서 `docker compose logs`로 충분하다.
- 수준은 INFO(상태 전이·기동·재시도), WARNING(수복된 실패), ERROR(수복 실패)로 구분한다. 자동 삭제(`FR-033`)는 삭제 파일 수·확보 용량을 INFO로 기록하여 추적 의무(`NFR-010`)를 이행한다.
- ***Request router***의 접근 로그는 쿼리 파라미터로 전달된 토큰(§6.2)을 마스킹하여 기록한다. 스트리밍 경로는 유효한 액세스 토큰을 로그에 끊임없이 남기므로, 진단 목적으로 로그가 복사·공유되더라도 살아 있는 인증 자격이 함께 이동하지 않아야 한다.
- 실시간 진단은 로그가 아니라 모니터링 스트림(§6.4 (4))의 몫이다. 로그는 사후 추적용이다.
- SRS `NFR-020`이 보류한 로그 수집·진단 명세는 이 절의 내용으로 충족되며, 별도의 요구사항 승격이 필요한 내용이 없으므로 SRS 환류는 하지 않는다.

# 8. 배포 설계 (Deployment Design)

## 8.1 컨테이너 구성 (Container Composition)

네 컴포넌트 서비스와 게이트웨이(§2.4 (8)) 모두 재시작 정책은 `unless-stopped`다(`NFR-018`).

|서비스|베이스|하드웨어 접근|볼륨|포트 공개|
|---|---|---|---|---|
|`gateway`|caddy 공식 이미지(`caddy:2`) + openssl|없음|`docker/gateway/Caddyfile`(ro)·`data/caddy`(Device CA·서빙 인증서)|8000/tcp (HTTPS)|
|`preflight`|`recorder` 이미지 재사용, 엔트리포인트만 교체|호스트 `/dev`·`/tmp`·`/etc/nv_tegra_release`·GStreamer 플러그인·tegra 라이브러리(모두 ro)|`docker/preflight/preflight.sh`(ro)|없음|
|`router`|python 3.11 slim + FastAPI|없음|`data/db/router`|없음|
|`streamer`|python 3.11 slim + MediaMTX 1.20.1 정적 바이너리(다단계 복사) + FastAPI|없음|`config`|8189/udp|
|`analyzer`|NanoLLM(jetson-containers)|NVDEC·GPU 장치, 호스트 GStreamer 플러그인·tegra 라이브러리(ro), NvSciIPC 소켓, host IPC|`data/models`·`data/state/analyzer`|없음|
|`recorder`|ubuntu 22.04 + GStreamer + FastAPI + ffmpeg|NVDEC·NVENC 장치, 호스트 GStreamer 플러그인·tegra 라이브러리(ro), NvSciIPC 소켓, host IPC|`data/clips`·`data/db/recorder`·`data/state/recorder`, tmpfs(`/run/babycat-segments`)|없음|

`preflight`는 기동 시 한 번 실행되고 종료하는 사전 검사다(`restart: "no"`). `analyzer`와 `recorder`는 `depends_on`의 `service_completed_successfully` 조건으로 그 성공을 기다리므로, 호스트에 L4T R36.4.x·장치 노드·NvSciIPC 소켓·tegra 라이브러리·NVIDIA GStreamer 요소 중 하나라도 없으면 두 서비스는 기동하지 않고 원인은 `preflight`의 로그에 남는다. 검사 항목은 2026-08-26~27의 실제 장애(`nvidia-l4t-gstreamer` 미설치, JetPack 6.2.2)에서 도출하였다. `analyzer`와 `recorder`의 하드웨어 접근 항목이 같은 것은 우연이 아니다 — 둘 다 `nvv4l2decoder` 경로를 쓰며, `recorder`는 `nvv4l2h264enc`를 위해 NVENC 장치가 더해진다(§2.4 (3)). 데이터 볼륨은 §5.3의 소유 구획대로 서비스별로 좁혀 마운트하여, 소유하지 않은 데이터가 컨테이너 안에서 보이지 않게 한다. 호스트의 `data/` 하위 디렉터리는 기동 전에 운영자 소유로 만들어 둔다(`README.md`) — 없으면 컨테이너 런타임이 root 소유로 만든다. 소스 코드는 볼륨으로 마운트하지 않으며 이미지에만 담는다(§8.2).

## 8.2 이미지 빌드 (Image Build)

- 현장 빌드를 전제한다(SRS §3.3). `gateway`는 공식 Caddy 이미지에 openssl과 기동 스크립트만 더한 얇은 이미지이며, 설정은 Caddyfile 마운트로 주입한다. `router`와 `streamer`는 같은 python slim 베이스를 공유하여 레이어 중복을 줄인다. `streamer` 이미지는 공식 MediaMTX 이미지에서 정적 바이너리를 다단계 복사(`COPY --from`)로 가져와 담으며, 버전 인상은 참조 태그의 변경이다. 베이스 이미지 태그와 pip 패키지 버전은 모두 고정한다(SRS §4.4).
- `analyzer`의 베이스(NanoLLM)는 크기가 지배적이므로, 소스 변경이 베이스 레이어를 무효화하지 않도록 의존 설치와 소스 복사를 레이어로 분리한다. 소스 변경은 재빌드로 반영한다.
- `analyzer`는 NanoLLM 베이스 이미지의 내부 배치에 의존한다 — 컴파일 결과 경로(`/data/models/mlc/dist/{모델}/ctx4096/…`)와 HF 스냅숏 경로로 캐시 유무를 판정하고, MLC가 부모 디렉터리를 만들지 않는 `dist/models`와 clip_trt의 TensorRT 캐시 디렉터리를 기동 시 미리 만들며, clip_trt가 `~`를 확장하지 않는 결함을 빌드 시 패치한다. 베이스 이미지가 바뀌면 이 세 가지를 재확인해야 한다.
- MediaMTX는 RTSP(TCP)·HLS·WebRTC·제어 API만 활성화한다(`config/mediamtx.yml`). 쓰지 않는 서버(RTMP·SRT·MoQ·재생·RTSP/UDP)는 끈다.
- VLM 모델의 사전 컴파일(SRS §3.2)은 이미지 빌드가 아니라 최초 기동의 런타임에 일어나며, 결과는 `data/models`에 캐시되어 재기동·재빌드와 무관하게 재사용된다. 이 분리 덕에 이미지 재빌드가 수십 분의 재컴파일을 유발하지 않는다.

## 8.3 설정 주입 (Configuration Injection)

주입 값은 `.env` 파일과 Compose의 환경 변수로 전달한다. 자격증명은 형상 관리에서 제외하며(SRS §3.6), 저장소에는 `.env.example` 템플릿만 둔다. 토큰 서명 비밀키(`NFR-013`)는 주입 대상이 아니다 — `router`가 최초 기동 시 생성하여 `data/db/router/jwt_secret`에 보관하며, 볼륨을 지우면 함께 사라져 모든 사용자가 재로그인한다. 기기가 여럿일 때 토큰을 공유하려면 CA와 같이 이 파일을 복사한다.

|변수|대상|필수|설명|
|---|---|---|---|
|`HOST_IP`|`streamer`·`gateway`|필수|외부 도달 가능 IP. WebRTC ICE 후보로 광고하고, TLS 인증서의 주소(SAN)로도 쓴다. 쉼표로 복수 지정할 수 있다(MediaMTX가 환경 변수의 쉼표 목록을 배열로 읽는다)|
|`TLS_EXTRA_HOSTS`|`gateway`|선택|TLS 인증서에 더할 주소·호스트명(공백 구분). `HOST_IP`·localhost는 항상 포함된다|
|`JWT_EXPIRY`·`REFRESH_EXPIRY`|`router`|선택|토큰 수명. 기본값은 SRS `FR-001`·`FR-002`의 600초·30일|
|`DEFAULT_USER`·`DEFAULT_PASS`|`router`|필수|최초 기동 시 1회 생성되는 초기 계정(SRS §3.2)|
|`VLM_MODELS`|`analyzer`|필수|후보 VLM 모델 목록(SRS §3.2)|
|`MAX_NEW_TOKENS`|`analyzer`|선택|생성 토큰 상한(§7.2)|
|`MIN_INFER_INTERVAL`|`analyzer`|선택|추론 시작 간격의 하한(초, SRS `FR-058`). 기본 0(자연 주기)|
|`INFERENCE_RETENTION_DAYS`|`recorder`|선택|추론 이력 보존 기간(SRS `FR-053`). 기본 90일|
|`TARGET_FPS`·`N_FRAMES`|`analyzer`|선택|프레임 추출 주기와 추론당 프레임 수(§7.2)|
|`VLM_LOAD_TIMEOUT`·`VLM_INFER_TIMEOUT`|`analyzer`|선택|모델 적재와 추론 1회의 상한 시간(초). 초과는 실패로 계수한다(§7.5)|
|`TZ`|전체|선택|컨테이너 로컬 시간대. 날짜 필터의 달력 기준(기본 Asia/Seoul)|
|`CORS_EXTRA_ORIGINS`|`router`|선택|기본 허용 규칙(localhost, 사설망 IP, `capacitor://localhost`) 밖에서 추가로 허용할 origin 목록|
|`TRIGGER_COOLDOWN`|`recorder`|선택|이벤트 묶음 처리 간격(SRS `FR-030`)|
|`TRIGGER_CLIP_DUR`·`TRIGGER_PRE_EVENT_SEC`·`TRIGGER_POST_EVENT_SEC`|`recorder`|선택|클립 창(§7.2). 사후 구간은 미설정 시 기본 길이를 따름|
|`CLIP_MIN_FREE_MB`·`CLIP_TARGET_FREE_MB`|`recorder`|선택|자동 정리 발동·회복 여유 수위(SRS `FR-033`)|
|`RECORDER_ENCODE_BITRATE`·`RECORDER_ENCODE_FPS`|`recorder`|선택|세그먼트 재인코딩 비트레이트와 소스 프레임레이트 가정(§4.4)|

TLS(§2.4 (8))의 서빙 인증서는 `gateway`가 기동 시 스스로 확보한다 — 기동 스크립트가 `HOST_IP`·`TLS_EXTRA_HOSTS`·localhost를 SAN 목록으로 삼아, 인증서가 없거나 그 목록이 바뀌었거나 만료 30일 이내이면 `issue-cert.sh`를 호출해 발급하고 `data/caddy/site/`에 둔다. 운영자의 발급 절차는 없으며, 설치는 `.env` 작성과 `docker compose up -d --build`로 끝난다. 호스트 준비는 `tools/setup-jetson.sh`(L4T 릴리스 확인, JetPack 구성 요소와 Docker 설치)와 기동 시의 `preflight`(검증)로 나뉜다.

CA는 제조사 Root CA → 기기별 Device CA → 서빙 인증서의 세 단계다. 보호자 한 명이 기기 여러 대를 운용해도 클라이언트가 CA 하나(Root)만 신뢰하면 되도록 하기 위함이며, 기기 사이에 파일을 옮기는 절차를 두지 않는다. Root CA의 개인키는 저장소 밖(개발 PC)에 보관하고, 출고 시 `tools/provision-device.sh`가 시리얼별 Device CA를 발급하여 기기의 `data/caddy/caddy/pki/authorities/local/`에 둔다. 발급 스크립트는 그 자리의 CA로 서명하므로 제품 기기와 개발 기기의 기동 절차는 같고, 파일이 없는 개발 기기만 자체 root CA를 생성한다. Device CA에는 사설 IPv4 대역·`localhost`·`.local`로 nameConstraints를 두어, 유출되어도 그 밖의 주소에 대한 인증서를 만들 수 없게 한다. `cert.pem`은 리프와 Device CA를 이어 붙인 체인이다 — 클라이언트는 Device CA를 모르기 때문이다. mewly는 Root CA를 리소스로 동봉하고 사용자 설치 CA도 신뢰하므로(network security config), 개발 기기의 자체 CA는 그 루트를 폰에 설치하면 접속된다. 절차와 키 보관 규칙은 `docs/ops/pki.md`에 있다.

다음 값은 Compose 파일이 고정하여 주입하며 운영자 조정 대상이 아니다. 컨테이너 안 경로와 내부 호스트명은 §5.3·§6.3의 배치와 일치한다.

|변수|대상|값|
|---|---|---|
|`DB_PATH`|`router`·`recorder`|`/data/db/router.db`·`/data/db/recorder.db`|
|`STATE_PATH`|`analyzer`·`recorder`|`/data/state/analyzer.json`·`/data/state/recorder.json`|
|`CLIP_DIR`|`recorder`|`/data/clips`|
|`TRIGGER_SEGMENT_DIR`|`recorder`|`/run/babycat-segments/live`|
|`MEDIAMTX_URL`|`analyzer`·`recorder`|`rtsp://streamer:8554/live`|
|`STREAMER_URL`·`ANALYZER_URL`·`RECORDER_URL`|`router`|`http://<서비스>:8080`|
|`STREAMER_HLS_URL`·`STREAMER_WEBRTC_URL`|`router`|`http://streamer:8888`·`http://streamer:8889`|

## 8.4 로그와 진단 (Logging and Diagnostics)

- 모든 서비스는 로그를 표준 출력으로 내보내고, 수집·보존은 컨테이너 런타임의 로그 드라이버(로테이션 설정 포함)에 맡긴다. 별도의 로그 수집 컴포넌트를 두지 않는다 — 단일 호스트·소수 운영자 전제에서 `docker compose logs`로 충분하다.
- 수준은 INFO(상태 전이·기동·재시도), WARNING(수복된 실패), ERROR(수복 실패)로 구분한다. 자동 삭제(`FR-033`)는 삭제 파일 수·확보 용량을 INFO로 기록하여 추적 의무(`NFR-010`)를 이행한다.
- ***Request router***의 접근 로그는 쿼리 파라미터로 전달된 토큰(§6.2)을 마스킹하여 기록한다. 스트리밍 경로는 유효한 액세스 토큰을 로그에 끊임없이 남기므로, 진단 목적으로 로그가 복사·공유되더라도 살아 있는 인증 자격이 함께 이동하지 않아야 한다.
- 실시간 진단은 로그가 아니라 모니터링 스트림(§6.4 (4))의 몫이다. 로그는 사후 추적용이다.
- 이 절은 SRS `NFR-020`의 로그 처리 방침(표준 출력 수집, 별도 컴포넌트 없음)을 실현한다.

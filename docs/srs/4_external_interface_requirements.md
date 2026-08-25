# 4. 외부 인터페이스 요구사항 (External Interface Requirements)

본 장은 `Babycat` 경계를 넘는 외부 인터페이스를 정의한다. 내부 컴포넌트 간 인터페이스(***Request router*** ↔ ***Video analyzer*** 등)는 설계 문서의 범위로 한다. 외부 인터페이스에는 `IF` 식별자를 부여한다.

|ID|인터페이스|당사자|프로토콜|
|---|---|---|---|
|`IF-001`|HTTP API|***Client app*** ↔ ***Request router***|HTTPS/JSON|
|`IF-002`|비디오 스트림 수신|***Video source*** → ***Video streamer***|RTSP (H.264)|
|`IF-003`|라이브 스트리밍|***Video streamer*** → ***Client app***|HLS/WebRTC|
|`IF-004`|PTZ 제어|***Video streamer*** → ***Video source***|ONVIF|

## 4.1 시스템 인터페이스 (System Interface)

### IF-001: HTTP API (***Client app*** ↔ ***Request router***)

***Client app***이 사용하는 단일 제어 진입점이다. 요청/응답 본문은 JSON이며, 인증이 필요한 엔드포인트는 `Authorization: Bearer <JWT>` 헤더를 요구한다(헤더를 설정할 수 없는 클라이언트 기능을 위해 `?token=` 쿼리 파라미터를 허용한다).

|엔드포인트|메서드|기능|인증|
|---|---|---|---|
|`/api/login`|POST|로그인. 액세스 토큰 발급(로그인 유지 요청 시 리프레시 토큰 포함).|불필요|
|`/api/refresh`|POST|리프레시 토큰으로 액세스 토큰 갱신(토큰 회전).|불필요|
|`/api/logout`|POST|로그아웃. 발급된 토큰 폐기.|불필요|
|`/api/change-password`|POST|비밀번호 변경.|필요|
|`/client/storage/{key}`|GET|클라이언트 데이터 문서 조회.|필요|
|`/client/storage/{key}`|PUT|클라이언트 데이터 문서 저장(전체 교체).|필요|
|`/health`|GET|서버 상태 확인.|불필요|
|`/camera`|GET|비디오 소스 프로필 조회(비밀번호 마스킹).|필요|
|`/camera`|POST|비디오 소스 프로필 등록(수정).|필요|
|`/streaming/start`|POST|라이브 스트리밍 시작. 재시작을 겸한다.|필요|
|`/streaming/stop`|POST|라이브 스트리밍 종료. 진행 중인 분석·버퍼링도 함께 정지.|필요|
|`/clips`|GET|클립 목록 조회(장면 설명 부분 일치, 날짜 필터, 페이지네이션).|필요|
|`/clips/{name}`|GET|클립 재생(HTTP Range 지원).|필요|
|`/clips`|DELETE|선택 클립 삭제.|필요|
|`/clips/all`|DELETE|전체 클립 삭제.|필요|
|`/events`|GET|이벤트 이력 조회(키워드, 날짜 필터, 페이지네이션).|필요|
|`/events/{id}`|DELETE|이벤트 이력 개별 삭제.|필요|
|`/events`|DELETE|이벤트 이력 전체 삭제.|필요|
|`/ptz`|POST|비디오 소스 PTZ 제어(이동/정지/절대 이동/프리셋 저장/프리셋 이동/자동 순찰 설정).|필요|
|`/prompt`|POST|VLM 프롬프트·이벤트 키워드 설정.|필요|
|`/analysis/start`|POST|비디오 분석 시작/재시작.|필요|
|`/analysis/stop`|POST|비디오 분석 종료. 라이브 스트리밍은 유지.|필요|
|`/vlm/switch`|POST|VLM 모델 전환(`P3`).|필요|
|`/state`|GET|시스템 상태 실시간 수신(SSE).|필요|
|`/stream`|GET|VLM 입력 프레임 수신(MJPEG, `P3`).|필요|
|`/live/hls/{path}`|GET|HLS 재생 중계.|필요|
|`/live/whep`|POST|WebRTC 시그널링(WHEP) 세션 수립 중계.|필요|
|`/live/whep/{session}`|PATCH/DELETE|WebRTC 시그널링 세션 갱신/종료 중계.|필요|

이벤트 푸시 알림용 디바이스 관리 API는 차기 버전으로 미룬다.

각 엔드포인트의 요청/응답 형식과 오류 코드는 설계 문서(SDD §6)가 정의하며, 별도의 인터페이스 요구사항 명세서는 두지 않는다.

### IF-002: 비디오 스트림 수신 (***Video source*** → ***Video streamer***)

- ***Video source***는 H.264로 인코딩된 비디오 스트림을 제공해야 한다.
- ***Video streamer***는 스트리밍 시작 시점에 등록되어 있던 프로필(§2.3 (3))의 RTSP URL(`rtsp://<user>:<pass>@<ip>:<port>/<path>`)로 연결하여 스트림을 수신한다.
- 발생 빈도: 라이브 스트리밍이 진행 중인 동안 상시 연결.
- 에러 처리: 연결 실패 시 접속을 재시도한다(`FR-046`).

### IF-003: 라이브 스트리밍 (***Video streamer*** → ***Client app***)

- 프로토콜: HLS/WebRTC.
- HLS 비디오와 WebRTC 시그널링은 ***Request router***를 경유하며, ***Request router***가 `IF-001`과 동일한 방식으로 인증한다. 별도의 스트림 접근 토큰은 두지 않으며, ***Video streamer***는 자체 접근 통제를 수행하지 않는다.
- WebRTC 미디어는 저지연을 위해 ***Request router***를 거치지 않고 ***Video streamer***가 ***Client app***에게 직접 전달한다. WebRTC는 외부 도달 가능한 IP를 ICE 후보로 광고하여 미디어 연결을 수립한다.

### IF-004: PTZ 제어 (***Video streamer*** → ***Video source***)

- 조건부 인터페이스이다. ***Video source***가 ONVIF PTZ를 지원하는 경우에 한한다.
- ***Video streamer***는 비디오 소스 프로필의 ONVIF 포트(`http://<ip>:<onvif_port>/onvif/service`)로 프로필 토큰 조회(GetProfiles), 연속 이동(ContinuousMove), 정지(Stop), 절대 이동(AbsoluteMove) 명령과 위치 조회(GetStatus)를 전달한다.
- 발생 빈도: 이동·정지·절대 이동은 사용자 입력 시, 위치 조회는 라이브 스트리밍 중 2초 주기, 자동 순찰(`FR-052`)이 활성이면 전환 간격마다 절대 이동.

## 4.2 사용자 인터페이스 (User Interface)

이 시스템에는 사용자 인터페이스 요구사항이 없다. `Babycat`은 백엔드이며 사용자 인터페이스는 ***Client app***의 책임이다. `Babycat`은 `IF-001`의 HTTP API만을 제공한다. ***Client app***의 예시 구현을 참조용으로 저장소에 함께 제공하나, 이는 제품 범위에 포함되지 않는다.

## 4.3 하드웨어 인터페이스 (Hardware Interface)

이 시스템에는 하드웨어 인터페이스 요구사항이 없다. 카메라 제어는 네트워크 프로토콜(`IF-004`)로 수행하며, Jetson Board의 하드웨어 가속 장치 사용은 운영 환경 요구사항에 해당한다.

## 4.4 소프트웨어 인터페이스 (Software Interface)

|이름|버전|출처|용도|
|---|---|---|---|
|MediaMTX|1.20.1|Docker Hub (`bluenviron/mediamtx`)|RTSP 수신, HLS/WebRTC 송신.|
|NanoLLM|`dustynv/nano_llm:r36.4.0`|jetson-containers|VLM 추론 스택(***Video analyzer*** 베이스 이미지).|
|GStreamer|1.x (베이스 이미지 및 호스트 NVIDIA 플러그인)|JetPack / 베이스 이미지|비디오 파이프라인(디코딩, 프레임 추출, 클립 인코딩).|
|SQLite|Python 내장 `sqlite3`|Python 표준 라이브러리|사용자, 토큰, 이벤트 영속화.|
|FastAPI / uvicorn|0.141.1 / 0.52.3|PyPI|***Request router***·***Video streamer***(동반 프로세스)·***Event recorder***의 HTTP 서버 프레임워크.|
|Caddy|2.11.4 (`caddy:2.11.4`)|Docker Hub (`caddy`)|TLS 종단 게이트웨이. 사설(내부) CA 운용과 인증서 발급.|

## 4.5 통신 인터페이스 (Communication Interface)

외부에 노출되는 포트는 다음과 같다. ***Video streamer***의 HLS·WebRTC 시그널링·RTSP 포트는 ***Request router***를 경유하므로 외부에 노출하지 않는다.

|포트|프로토콜|컴포넌트|용도|
|---|---|---|---|
|8000/tcp|HTTPS|`gateway` → ***Request router***|단일 외부 진입점. TLS 종단 게이트웨이가 제어(`IF-001`) 및 HLS·WebRTC 시그널링 중계(`IF-003`)를 ***Request router***로 전달.|
|8189/udp|UDP|***Video streamer***|WebRTC 미디어/ICE(`IF-003`). 프로토콜 자체의 DTLS-SRTP로 암호화.|

- 위 포트는 운영 네트워크의 방화벽에서 개방되어야 한다.
- 8000/tcp의 TLS 인증서는 사설(내부) CA가 발급한다(`NFR-016`). 클라이언트 기기는 제조사 루트 CA를 신뢰하며, 개발 기기의 자체 CA는 그 루트 인증서를 신뢰 저장소에 1회 등록해야 한다.

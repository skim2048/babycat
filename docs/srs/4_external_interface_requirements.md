# 4. 외부 인터페이스 요구사항 (External Interface Requirements)

본 장은 `Babycat` 경계를 넘는 외부 인터페이스를 정의한다. 내부 컴포넌트 간 인터페이스(***Gateway*** ↔ ***Engine*** 등)는 설계 문서의 범위로 한다. 외부 인터페이스에는 `IF` 식별자를 부여한다(§1.2).

|ID|인터페이스|당사자|프로토콜|
|---|---|---|---|
|`IF-001`|HTTP API|***Client App*** ↔ ***Gateway***|HTTP/JSON|
|`IF-002`|비디오 스트림 수신|***Video Source*** → ***Media***|RTSP (H.264)|
|`IF-003`|라이브 스트리밍|***Media*** → ***Client App***|HLS, WebRTC|
|`IF-004`|PTZ 제어|***Engine*** → ***Video Source***|ONVIF|

## 4.1 시스템 인터페이스 (System Interface)

### IF-001: HTTP API (***Client App*** ↔ ***Gateway***)

***Client App***이 사용하는 단일 제어 진입점이다. 요청/응답 본문은 JSON이며, 인증이 필요한 엔드포인트는 `Authorization: Bearer <JWT>` 헤더를 요구한다(헤더를 설정할 수 없는 클라이언트 기능을 위해 `?token=` 쿼리 파라미터를 허용한다).

|엔드포인트|메서드|기능|인증|
|---|---|---|---|
|`/api/login`|POST|로그인. JWT 및 리프레시 토큰 발급.|불필요|
|`/api/refresh`|POST|리프레시 토큰으로 액세스 토큰 갱신(토큰 회전).|불필요|
|`/api/logout`|POST|리프레시 토큰 폐기.|불필요|
|`/api/change-password`|POST|비밀번호 변경.|필요|
|`/health`|GET|서버 상태 확인.|불필요|
|`/camera`|GET|카메라 프로필 조회(비밀번호 마스킹).|필요|
|`/camera`|POST|카메라 프로필 적용.|필요|
|`/clips`|GET|클립 목록 조회(키워드, 날짜 필터, 페이지네이션).|필요|
|`/clips/{name}`|GET|클립 재생(HTTP Range 지원).|필요|
|`/clips`|DELETE|선택 클립 삭제.|필요|
|`/clips/all`|DELETE|전체 클립 삭제.|필요|
|`/events`|GET|이벤트 이력 조회(페이지네이션).|필요|
|`/events`|DELETE|이벤트 이력 전체 삭제.|필요|

다음 엔드포인트는 재설계에서 ***Gateway***로 통합되어야 하는 것들로, 경로와 명세는 작성을 보류한다.

|기능|현재 위치|비고|
|---|---|---|
|PTZ 제어|***Engine*** 직접 노출|단일 진입점 원칙에 따라 ***Gateway*** 경유로 변경(§2.2).|
|VLM 프롬프트, 이벤트 키워드 설정|***Engine*** 직접 노출|장면 분석 설정에 해당하는 경로(§2.4).|
|스트림 접속 정보 발급(URL + JWT)|신규|라이브 스트리밍 접근 토큰 발급 경로(§2.4).|
|시스템 상태 실시간 수신(SSE)|***Engine*** 직접 노출|추론 결과 및 하드웨어 상태.|

이벤트 푸시 알림용 디바이스 관리 API는 차기 버전으로 미룬다(§2.8).

각 엔드포인트의 상세 명세(요청/응답 스키마, 에러 코드)는 작성을 보류한다 — 본 문서 부록 또는 별도 IRS 문서로의 분리를 검토한다.

### IF-002: 비디오 스트림 수신 (***Video Source*** → ***Media***)

- ***Video Source***는 H.264로 인코딩된 비디오 스트림을 제공해야 한다(§2.7).
- ***Media***는 저장된 카메라 프로필의 RTSP URL(`rtsp://<user>:<pass>@<ip>:<port>/<path>`)로 TCP 연결하여 스트림을 수신한다.
- 발생 빈도: 카메라 프로필이 활성화된 동안 상시 연결.
- 에러 처리: 연결 실패 시 재시도한다. 재시도 정책은 작성을 보류한다.

### IF-003: 라이브 스트리밍 (***Media*** → ***Client App***)

- ***Client App***은 ***Gateway***에서 발급받은 JWT를 사용하여 ***Media***에 직접 연결한다(§2.4).
- 프로토콜: HLS(HTTP) 또는 WebRTC. WebRTC는 ICE 후보로 광고된 `HOST_IP`로 미디어 연결을 수립한다.
- ***Media***는 JWT 검증에 성공한 경우에만 스트림을 송신한다. JWT 전달 방식(Authorization 헤더 또는 쿼리 파라미터)은 작성을 보류한다.

### IF-004: PTZ 제어 (***Engine*** → ***Video Source***)

- 조건부 인터페이스이다. ***Video Source***가 ONVIF PTZ를 지원하는 경우에 한한다(§2.4).
- ***Engine***은 카메라 프로필의 ONVIF 포트(`http://<ip>:<onvif_port>/onvif/service`)로 이동(continuous move)/정지 명령을 전달한다.
- 발생 빈도: 사용자 입력 시에만 발생.

## 4.2 사용자 인터페이스 (User Interface)

이 시스템에는 사용자 인터페이스 요구사항이 없다. `Babycat`은 백엔드이며 사용자 인터페이스는 ***Client App***의 책임이다. `Babycat`이 제공하는 것은 `IF-001`의 HTTP API뿐이다.

## 4.3 하드웨어 인터페이스 (Hardware Interface)

이 시스템에는 하드웨어 인터페이스 요구사항이 없다. 카메라 제어는 네트워크 프로토콜(`IF-004`)로 수행하며, Jetson Board의 하드웨어 가속 장치 사용은 운영 환경 요구사항(§3.1)에 해당한다.

## 4.4 소프트웨어 인터페이스 (Software Interface)

|이름|버전|출처|용도|
|---|---|---|---|
|MediaMTX|작성 보류 (현재 `latest` 사용 중 — 버전 고정 필요)|Docker Hub (`bluenviron/mediamtx`)|RTSP 수신, HLS/WebRTC 송신. ***Engine***이 제어 API(v3)로 소스를 설정한다.|
|NanoLLM|`dustynv/nano_llm:r36.4.0`|jetson-containers|VLM 추론 스택(***Engine*** 베이스 이미지).|
|GStreamer|1.x (베이스 이미지 및 호스트 NVIDIA 플러그인)|JetPack / 베이스 이미지|비디오 파이프라인(디코딩, 프레임 추출, 클립 인코딩).|
|SQLite|Python 내장 `sqlite3`|Python 표준 라이브러리|사용자, 토큰, 이벤트 영속화(§6.4).|
|FastAPI / uvicorn|작성 보류 (버전 고정 필요)|PyPI|***Gateway*** 프레임워크.|

공유 데이터: ***Gateway***와 ***Engine***은 `/data` 파일시스템(클립 mp4/json, SQLite DB, 카메라 프로필 JSON)을 바인드 마운트로 공유한다. 접근 권한은 §2.3를 따른다.

## 4.5 통신 인터페이스 (Communication Interface)

외부에 노출되는 포트는 다음과 같다.

|포트|프로토콜|컴포넌트|용도|
|---|---|---|---|
|8000/tcp|HTTP|***Gateway***|단일 제어 진입점(`IF-001`).|
|8888/tcp|HTTP|***Media***|HLS 스트리밍(`IF-003`).|
|8889/tcp|HTTP|***Media***|WebRTC 시그널링(`IF-003`).|
|8890/udp|UDP|***Media***|WebRTC ICE.|
|8554/tcp|RTSP|***Media***|RTSP 수신/재배포.|

- ***Engine***의 HTTP 포트(8080)는 내부 전용이며 재설계에서 외부에 노출하지 않는다.
- 위 포트는 운영 네트워크의 방화벽에서 개방되어야 한다(§6.9).
- 전송 계층 암호화(HTTPS/TLS) 적용 여부는 작성을 보류한다.

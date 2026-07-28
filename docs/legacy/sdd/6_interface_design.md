# 6. 인터페이스 설계 (Interface Design)

## 6.1 외부 API (External API)

***Request router***가 노출하는 전체 표면이다. 인증 열의 "필요"는 §6.2의 검증을 통과해야 함을 뜻한다. 요청·응답 본문은 JSON이다(스트림 응답 제외).

### 사용자 계정 인증 및 관리

|경로|메서드|기능|인증|전달 대상|
|---|---|---|---|---|
|`/api/login`|POST|로그인. 액세스·리프레시 토큰 발급.|불필요|`router` 자체|
|`/api/refresh`|POST|리프레시 토큰으로 액세스 토큰 갱신(회전).|불필요|`router` 자체|
|`/api/logout`|POST|토큰 폐기.|불필요|`router` 자체|
|`/api/change-password`|POST|비밀번호 변경(기존 토큰 전체 폐기).|필요|`router` 자체|
|`/health`|GET|서버 상태 확인.|불필요|`router` 자체|

### 비디오 소스 프로필·PTZ

|경로|메서드|기능|인증|전달 대상|
|---|---|---|---|---|
|`/camera`|GET|비디오 소스 프로필 조회(비밀번호 마스킹).|필요|`streamer`|
|`/camera`|POST|비디오 소스 프로필 적용.|필요|`streamer`|
|`/ptz`|POST|팬·틸트·줌 이동/정지/홈 저장/홈 복귀.|필요|`streamer`|

### 장면 분석

|경로|메서드|기능|인증|전달 대상|
|---|---|---|---|---|
|`/prompt`|POST|VLM 프롬프트·이벤트 키워드 설정. 분석을 시작하지 않는다(`FR-025`).|필요|`analyzer`|
|`/analysis/start`|POST|장면 분석 시작/재시작(`FR-024`). `analyzer`·`streamer`·`recorder`에 병렬 전달(SRS §2.3 (4)).|필요|셋 모두|
|`/vlm/switch`|POST|VLM 모델 전환(`FR-032`, `P3`).|필요|`analyzer`|

### 모니터링

|경로|메서드|기능|인증|전달 대상|
|---|---|---|---|---|
|`/state`|GET|모니터링 스트림(SSE). §6.4 (4)의 합성 결과.|필요|합성|
|`/stream`|GET|VLM 입력 프레임 MJPEG(`FR-044`, `P3`).|필요|`analyzer`|

### 클립·이력

|경로|메서드|기능|인증|전달 대상|
|---|---|---|---|---|
|`/clips`|GET|클립 목록 조회(부분 일치 텍스트·날짜, 페이지네이션).|필요|`recorder`|
|`/clips/{name}`|GET|클립 재생(HTTP Range 지원).|필요|`recorder`|
|`/clips`|DELETE|선택 클립 삭제.|필요|`recorder`|
|`/clips/all`|DELETE|전체 클립 삭제.|필요|`recorder`|
|`/events`|GET|발생 이력 조회(키워드·날짜, 페이지네이션).|필요|`recorder`|
|`/events/{id}`|DELETE|발생 이력 개별 삭제(`FR-035`).|필요|`recorder`|
|`/events`|DELETE|발생 이력 전체 삭제.|필요|`recorder`|

### 라이브 스트리밍 중계

|경로|메서드|기능|인증|전달 대상|
|---|---|---|---|---|
|`/live/hls/{path}`|GET|HLS 재생목록·세그먼트 중계.|필요|`streamer`|
|`/live/whep`|POST|WebRTC 세션 수립(WHEP).|필요|`streamer`|
|`/live/whep/{session}`|PATCH·DELETE|ICE 갱신·세션 종료.|필요|`streamer`|

`/analysis/start`는 멱등이다. 시작 요청은 재시작을 겸하므로(`FR-024`), 부분 실패 시 ***Request router***는 오류로 응답하되 이미 성공한 컴포넌트를 되돌리지 않으며, ***Client app***의 재요청이 수복 수단이 된다.

## 6.2 인증과 토큰 (Authentication and Tokens)

- **액세스 토큰** — HMAC-SHA256 서명 JWT. 페이로드는 사용자 식별자, 만료 시각(발급 후 600초), 세대(epoch)다. ***Request router***가 발급과 검증을 모두 수행하며, 서명 비밀키는 이 컴포넌트에만 주입한다(§2.3).
- **리프레시 토큰** — 임의 난수 토큰. 로그인 유지를 요청한 로그인에서만 발급한다(`FR-002`). 원문은 클라이언트만 보관하고 서버는 해시만 저장하며, 만료는 발급 후 30일이다. 갱신마다 회전한다(`FR-045`).
- **폐기** — 로그아웃과 비밀번호 변경 시 ***Request router***가 계정의 세대를 증가시킨다. 매 인증마다 토큰의 세대를 계정 데이터베이스의 현재 세대와 대조하므로, 이전 세대의 액세스 토큰은 즉시 거부된다(`FR-003`·`FR-005`). 발급·검증·폐기가 한 프로세스에 있어 이 대조는 자기 데이터베이스 읽기 한 번이다.
- **토큰 전달** — 원칙은 `Authorization: Bearer` 헤더이고, 헤더를 설정할 수 없는 클라이언트 기능(HLS·SSE·MJPEG·클립 재생)을 위해 `?token=` 쿼리 파라미터를 허용한다.
- **스트림 접근 토큰은 존재하지 않는다** — 단일 진입점 결정(§2.4 (2))으로 모든 재생 요청이 위 검증을 거치므로, 별도 토큰과 그 폐기 지연 문제가 성립하지 않는다.
- **초기 계정** — 최초 기동 시 초기 관리자 계정을 1회 생성하고, 초기 비밀번호가 변경되지 않은 동안 로그인 응답에 변경 필요를 명시한다(`FR-006`). 로그인 연속 10회 실패 시 30분 차단한다(`FR-007`).

## 6.3 컴포넌트 간 인터페이스 (Inter-component Interface)

내부 호출은 컨테이너 네트워크의 HTTP이며 인증을 두지 않는다(§2.2). 내부 포트는 `streamer`의 동반 프로세스 8200, `analyzer` 8300, `recorder` 8400이며 어느 것도 호스트에 공개하지 않는다. 계정 인증은 ***Request router***의 내부 기능이므로 컴포넌트 간 인터페이스가 아니다.

|제공자|경로|호출자|기능|
|---|---|---|---|
|`streamer`(동반 프로세스)|GET·POST `/profile`|`router`|프로필 조회·적용|
|`streamer`(동반 프로세스)|POST `/ptz`|`router`|PTZ 명령|
|`streamer`(동반 프로세스)|POST `/activate`|`router`|저장된 프로필로 소스 재배포 확인(분석 시작의 일부)|
|`streamer`(동반 프로세스)|GET `/status`|`router`|PTZ 위치 상태(모니터링 합성용)|
|`analyzer`|POST `/prompt`·`/start`·`/vlm/switch`|`router`|분석 설정·시작·모델 전환|
|`analyzer`|GET `/events`(SSE)·`/stream`(MJPEG)|`router`|분석 상태 스트림·입력 프레임|
|`recorder`|POST `/notify`|`analyzer`|이벤트 통지(매칭 키워드·장면 설명·발생 시각)|
|`recorder`|POST `/buffer/start`|`router`|세그먼트 버퍼 시작(분석 시작의 일부)|
|`recorder`|GET·DELETE `/clips`(계열)·`/events`(계열)|`router`|§6.1 클립·이력 기능의 실체|
|`recorder`|GET `/status`|`router`|하드웨어·저장·세그먼트 상태(모니터링 합성용)|
|`streamer`(MediaMTX)|HLS(8888)·WHEP(8889)|`router`|재생 중계의 상류|
|`streamer`(MediaMTX)|RTSP(8554)|`analyzer`·`recorder`|재배포 스트림 수신|

MediaMTX 제어 API(9997)는 동반 프로세스가 같은 컨테이너 안에서 localhost로 호출하는 프로세스 간 인터페이스이므로 이 표에 넣지 않는다(§4.2).

이벤트 통지(`/notify`)의 본문은 매칭 키워드 목록, 장면 설명 텍스트, 판정 시각, VLM이 본 마지막 프레임의 캡처 시각, 그리고 진단용 추론 시각 정보다. 프레임 캡처 시각은 클립 창의 기준점이므로 계약 필드다(§7.2). ***Event recorder***는 수신 즉시 응답하고 클립 결합은 작업 스레드에서 수행한다(§3.4). 통지가 유실되면 해당 이벤트는 기록되지 않으며, 이를 좁히는 재전송은 두지 않는다 — 추론 주기가 수 초이므로 지속되는 상황은 다음 추론에서 다시 판정된다.

## 6.4 스트리밍 인터페이스 (Streaming Interface)

### (1) RTSP 수신

***Video streamer***는 프로필의 RTSP URL로 ***Video source***에 접속하여 수신한다(`IF-002`). ***Video analyzer***와 ***Event recorder***는 각자 독립된 RTSP 연결로 재배포 스트림(`rtsp://streamer:8554/live`)을 소비한다. 접속 실패의 재시도(`FR-046`)는 간격을 늘려가며 무한 반복하되 실현 수단은 컴포넌트별로 다르다 — ***Event recorder***는 기록 파이프라인 재기동을 초기 1초에서 2배씩 상한 10초로, ***Video analyzer***는 워치독 재시작 간격을 기본 15초에서 2배씩 상한 60초로 늘리며, 프레임이 흐르기 시작하면 기본 간격으로 복귀한다. 소스 적용의 재시도(`FR-015`)는 `streamer`의 동반 프로세스가 같은 컨테이너의 MediaMTX를 상대로 수행하는 내부 절차다(§4.2).

### (2) HLS·WHEP 중계

- HLS: ***Request router***가 `/live/hls/{path}`를 `streamer`의 HLS 서버로 중계한다. MediaMTX의 재생목록은 상대 URL을 쓰므로 본문 재작성이 필요 없다.
- WHEP: `POST /live/whep`를 중계하고, 응답의 `Location` 헤더(세션 자원 경로)를 ***Request router*** 경로로 재작성한다. 이후의 `PATCH`(ICE 후보)·`DELETE`(종료)도 같은 경로로 중계한다.
- SSE·MJPEG 중계를 포함한 모든 스트림 중계는 버퍼링 없이 도착분을 즉시 전달한다. 유휴 SSE가 정체로 오인되지 않도록 중계 읽기에 타임아웃을 두지 않는다.

### (3) WebRTC 미디어 직접 경로

시그널링에서 교환된 ICE 자격으로 ***Client app***과 ***Video streamer*** 사이에 UDP(8189) 미디어 연결이 직접 수립된다. ***Video streamer***는 외부 도달 가능한 호스트 IP를 ICE 후보로 광고한다(SRS §3.2).

### (4) 모니터링 스트림 합성

`FR-042`·`FR-043`의 실시간 제공은 ***Request router***의 합성으로 실현한다. ***Request router***는 `analyzer`의 SSE를 구독하여 추론·파이프라인 상태 변화를 즉시 받고, `recorder`와 `streamer`의 `/status`를 주기(2초)로 수집하여, 세 출처를 하나의 평면 JSON 스냅숏으로 병합해 `/state` SSE로 내보낸다. 어느 출처가 응답하지 않으면 해당 필드 그룹을 결측으로 표시하고 나머지는 계속 전달한다 — 관측은 부분 실패에도 살아 있어야 한다(§2.1 목표 3).

## 6.5 오류 응답 규약 (Error Response Convention)

- 오류 본문은 `{"detail": <문자열>}` 하나로 통일한다.
- 상태 코드: 400(요청 형식 오류), 401(인증 실패·폐기된 토큰), 404(대상 부재), 429(로그인 차단, `FR-007`), 502(내부 컴포넌트 무응답·서버 오류).
- 내부 컴포넌트의 5xx와 무응답은 ***Request router***가 502로 정규화한다. 4xx는 의미를 보존한 채 그대로 전달한다.
- 인증 없는 요청이 인증 필요 경로에 닿으면 기능을 불문하고 401이다(`FR-008`).

# 3. Interfaces; 인터페이스

본 절은 컴포넌트 사이의 **인터페이스(계약)**를 기술한다. 각 인터페이스는 §1의 그림 1-1에 화살표로 표기된 연결에 대응하며, 태그 (1)~(11)로 가리킨다. §2가 각 컴포넌트의 책임을 다뤘다면, 본 절은 그 컴포넌트들이 *서로 무엇을 어떻게 주고받는가*를 다룬다.

## 3.1 Conventions; 규약

- **방향** — 화살표는 데이터가 흐르는 방향이 아니라 **요청을 개시하는 방향**을 가리킨다. 한쪽만 개시하면 단방향(개시자 → 수신자), 양 끝이 서로 개시할 수 있으면 양방향(↔)이다.
- **공개 범위** — 인터페이스가 도달 가능한 범위.
  - `Babycat 외부 공개` — 호스트에 게시되어 ***Client App***이 직접 접근.
  - `Babycat 내부 전용` — Docker 내부망에서만 도달.
  - `RTSP Source 외부 공개` — ***RTSP Source*** 측이 LAN에 노출하는 포트에 Babycat이 접속.
- 괄호 친 포트(예: `(554)`)는 소스마다 달라질 수 있는 기본값이다.

## 3.2 Interface Catalog; 인터페이스 목록

|태그|방향|인터페이스|포트|공개 범위|
|---|---|---|---|---|
|(1)|***Client App*** → ***API Server***|HTTP|8000|Babycat 외부 공개|
|(2)|***API Server*** → ***App Server***|HTTP|8080|Babycat 내부 전용|
|(3)|***App Server*** → ***MediaMTX Server***|HTTP|9997|Babycat 내부 전용|
|(4)|***App Server*** → ***RTSP Source***|ONVIF|(2020)|RTSP Source 외부 공개|
|(5)|***RTSP Source*** ↔ ***MediaMTX Server***|RTSP|(554)|RTSP Source 외부 공개|
|(6)|***MediaMTX Server*** ↔ ***App Server***|RTSP|8554|Babycat 내부 전용|
|(7)|***Client App*** → ***MediaMTX Server***|HLS|8888|Babycat 외부 공개|
|(8)|***Client App*** → ***MediaMTX Server***|WebRTC Signaling|8889|Babycat 외부 공개|
|(9)|***Client App*** ↔ ***MediaMTX Server***|WebRTC Media·ICE|8890|Babycat 외부 공개|
|(10)|***API Server*** ↔ ***Storage***|Filesystem|-|Babycat 내부 전용|
|(11)|***App Server*** ↔ ***Storage***|Filesystem|-|Babycat 내부 전용|

인터페이스는 성격에 따라 제어 평면(§3.3), 미디어 평면(§3.4), 자원 접근(§3.5)으로 나뉜다. 각 인터페이스의 엔드포인트 단위 상세 명세(요청·응답 스키마)는 관련 설계 결정이 확정된 뒤 본 절에 보강한다.

## 3.3 Control Plane; 제어 평면

요청·응답으로 동작하는 동기적 인터페이스이다.

- **(1)** ***Client App*** → ***API Server*** · HTTP 8000 — 인증·계정·클립·이벤트 조회, RTSP Source 프로필, VLM 설정 등 모든 클라이언트 제어 요청의 진입점. 본문은 JSON이며 인증 토큰을 헤더로 동반한다.
- **(2)** ***API Server*** → ***App Server*** · HTTP 8080 — API가 ***App Server*** 소관 요청을 프록시한다. 본문은 JSON이며 클라이언트의 인증 토큰을 전달한다. **어떤 App 엔드포인트를 이 계약으로 노출할지(프록시 표면)는 미결이다(D-D).** 현행 구현은 프로필(`/camera`)만 프록시하며, PTZ·VLM 설정·모니터링 피드는 아직 포함되지 않는다.
- **(3)** ***App Server*** → ***MediaMTX Server*** · HTTP 9997 — MediaMTX 제어 API로 소스 경로(path)를 설정한다. 본문은 JSON.
- **(4)** ***App Server*** → ***RTSP Source*** · ONVIF(HTTP/SOAP) 2020 — PTZ를 제어한다. ONVIF 지원 소스에 한하며, 포트는 소스마다 다르다.

## 3.4 Media Plane; 미디어 평면

연속 미디어가 흐르는 인터페이스이다. 제어 평면과 달리 ***Client App***은 라이브 영상을 ***API Server***가 아니라 ***MediaMTX Server***에서 직접 받는다.

- **(5)** ***RTSP Source*** ↔ ***MediaMTX Server*** · RTSP 554 — ***MediaMTX Server***가 소스 URL로 접속해 H.264 스트림을 당겨온다. RTSP는 양 끝이 에이전트라 양방향으로 표기한다.
- **(6)** ***MediaMTX Server*** ↔ ***App Server*** · RTSP 8554 — ***App Server***가 추론용 영상을 당겨온다. (5)와 같이 RTSP 양방향이다.
- **(7)** ***Client App*** → ***MediaMTX Server*** · HLS 8888 — HLS로 라이브 영상을 재생한다. ***Client App***이 개시(GET)하고 영상은 응답으로 흐른다.
- **(8)** ***Client App*** → ***MediaMTX Server*** · WebRTC Signaling 8889 — WHEP(HTTP) 기반 세션 협상(SDP 교환·ICE 후보 전달).
- **(9)** ***Client App*** ↔ ***MediaMTX Server*** · WebRTC Media·ICE 8890/UDP — ICE 연결성 점검과 SRTP 미디어·SRTCP 피드백이 UDP에 다중화되어 양방향으로 오간다.
- **미결(D-B)** — 미디어 평면의 접근을 어떻게 인증할지는 정해지지 않았다. 라이브 스트리밍이 (7)~(9)처럼 ***MediaMTX Server*** 직결로 남을지, 일부가 ***API Server***를 경유할지도 이 결정에 달려 있다.

## 3.5 Resource Access; 자원 접근

능동 컴포넌트가 수동 자원 ***Storage***를 읽고 쓰는 접근으로, 네트워크가 아니라 파일시스템 경로이다(포트 없음, 방향 없이 `rw`).

- **(10)** ***API Server*** ↔ ***Storage*** · Filesystem — 사용자·기기·이벤트 DB(SQLite)와 클립 파일을 직접 조회·관리.
- **(11)** ***App Server*** ↔ ***Storage*** · Filesystem — RTSP Source 프로필, 이벤트 클립·롤오버 세그먼트·메타데이터를 기록.
- **미결(D-C)** — ***API Server***와 ***App Server***가 같은 SQLite·파일 트리를 공유하므로, 동시 접근과 이벤트 기록 주체에 관한 데이터 계약이 필요하다. 구체는 §5에서 정한다.

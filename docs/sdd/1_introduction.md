# 1. 개요 (Introduction)

## 1.1 목표 (Purpose)

이 문서는 `Babycat`의 소프트웨어 설계를 기술한다. SRS가 시스템이 무엇을 해야 하는지를 정했다면, 이 문서는 그것을 어떻게 만들지를 정한다. SRS의 모든 요구사항은 이 문서의 설계로 실현되며, 그 대응은 §9가 보인다. 설계가 SRS와 어긋나는 것을 발견하면 이 문서를 고칠 것이 아니라 SRS 개정을 먼저 논해야 한다 — SRS가 권위다.

## 1.2 범위 (Scope)

설계 대상은 SRS §2.2의 네 구성요소(***Request router***·***Video streamer***·***Video analyzer***·***Event recorder***)와 그 배포 구성이다. 다음은 설계에서 제외한다.

- ***Client app***의 내부 — `Babycat`은 백엔드이며, 별도로 관리하는 참조 구현 대시보드는 검증 수단일 뿐 설계 대상이 아니다.
- ***Video source*** 장비 자체와 그 설정.
- VLM 모델의 내부 구조와 품질 — 모델은 교체 가능한 외부 산출물로 취급한다.

## 1.3 문서 규칙 (Document Conventions)

- 요구사항 식별자와 우선순위 표기는 SRS §1.3을 따른다.
- 컴포넌트는 ***Request router***처럼 굵은 기울임으로, 컨테이너·서비스·코드 식별자는 `router`처럼 고정폭으로 적어 두 층위를 구분한다.
- 장·절 참조는 § 기호를 쓴다. 표기가 §만 있으면 이 문서의 절이고, SRS의 절은 "SRS §"로 구분한다.
- 대안이 있었던 설계 결정은 §2.4에 결정·대안·근거·손실의 형식으로 기록하며, 본문 각 절은 결정 번호로 이를 참조한다.
- 시퀀스 다이어그램은 mermaid로 본문에 포함하고, 아키텍처 그림은 `figs/`의 drawio SVG를 쓰되 mermaid 원본을 함께 둔다.

## 1.4 용어 및 약어 (Terms and Abbreviations)

SRS §1.4에 이미 있는 용어는 반복하지 않는다. 설계 단계에서 새로 등장하는 용어만 적는다.

|용어|설명|
|---|---|
|WHEP(WebRTC-HTTP Egress Protocol)|HTTP로 WebRTC 재생 세션을 수립하는 시그널링 규약|
|SSE(Server-Sent Events)|HTTP 연결 하나로 서버가 이벤트를 계속 내보내는 단방향 스트림|
|MJPEG(Motion JPEG)|JPEG 프레임을 연속 전송하는 단순 비디오 스트림|
|NVDEC/NVENC|Jetson SoC의 하드웨어 비디오 디코더/인코더|
|세대(epoch)|토큰 즉시 폐기를 위한 계정 단위 정수. 증가하면 이전 토큰이 모두 무효가 된다(§6.2)|
|세그먼트|사전 구간 확보를 위해 1초 단위로 쪼개 tmpfs에 두는 짧은 비디오 파일(§4.4)|
|동반 프로세스(companion process)|기성품 프로세스와 같은 컨테이너에서 함께 동작하며 그 제어·부가 기능을 맡는 프로세스. `streamer` 컨테이너의 프로필·PTZ 담당 프로세스가 이에 해당한다(§4.2)|
|tmpfs|디스크가 아닌 메모리에 존재하는 휘발성 파일시스템|
|WAL(Write-Ahead Logging)|SQLite의 저널 모드. 쓰기 중에도 읽기를 막지 않는다|

## 1.5 관련 문서 (Related Documents)

- SRS — `docs/srs/` (이 문서의 상위 권위)
- 작업 기록 — `workflow/` (설계 결정의 경위, 형상 관리 제외)
- MediaMTX 공식 문서 — ***Video streamer*** 설정·제어 API·WHEP의 준거
- ONVIF Profile S 사양 — PTZ 제어(`IF-004`)의 준거
- jetson-containers / NanoLLM — `analyzer` 베이스 이미지의 준거
- 설치 가이드 — 작성 예정(SRS §3.2)

## 1.6 대상 독자 및 읽는 법 (Intended Audience and Reading Suggestions)

- **구현자** — §2(왜 이렇게 설계했는가) → §3(전체 구조) → 담당 컴포넌트의 §4 절 → §5·§6(데이터·인터페이스 계약) → §7(동작·오류) 순서로 읽는다.
- **운영자** — §3.5(기동)와 §8(배포·설정·로그)만으로 충분하다.
- **검토자** — §2.4의 결정 목록과 §9의 추적표에서 출발하여, 관심 있는 결정의 본문 절로 들어간다.

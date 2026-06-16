# 2. Components and Responsibilities; 컴포넌트와 책임

SRS 2.2의 네 내부 컴포넌트에 대하여 설계 관점에서 책임을 정의한다. (작성 예정)

| 컴포넌트 | 책임 | 비고 |
|---|---|---|
| API Server | 단일 진입점. Client App의 HTTP 요청 처리. | 작성 예정 |
| App Server | VLM 추론, 이벤트 감지, 클립 저장, 카메라/소스 제어. | 작성 예정 |
| MediaMTX Server | RTSP 수신·재배포(HLS/WebRTC). | 작성 예정 |
| Storage | 클립·메타데이터·DB·카메라 프로필 영속화. | 작성 예정 |

> **메모 (단일 진입점 검토 시 참고, 미결 D-A).** App Server는 8080 포트에 API Server와 평행한 인증 HTTP API를 독자적으로 노출한다. `/camera`, `/clips` 등은 API Server에도 같은 이름으로 존재하며, App Server가 이를 `verify_jwt`로 직접 검문한다. 이는 "API Server 단일 진입점"(SRS 2.7) 원칙과 현재 구현이 어긋나 있음을 의미한다. 2·5·6·7번 기능의 경로를 그릴 때 다시 마주칠 지점이다.

# 2. Components and Responsibilities; 컴포넌트와 책임

SRS 2.2의 네 내부 컴포넌트에 대하여 설계 관점에서 책임을 정의한다. (작성 예정)

| 컴포넌트 | 책임 | 비고 |
|---|---|---|
| API Server | 단일 진입점. Client App의 HTTP 요청 처리. | 작성 예정 |
| App Server | VLM 추론, 이벤트 감지, 클립 저장, 카메라/소스 제어. | 작성 예정 |
| MediaMTX Server | RTSP 수신·재배포(HLS/WebRTC). | 작성 예정 |
| Storage | 클립·메타데이터·DB·카메라 프로필 영속화. | 작성 예정 |

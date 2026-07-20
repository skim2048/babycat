# 6. 인터페이스 설계 (Interface Design)

## 6.1 외부 API (External API)

<!-- Client App에게 노출하는 HTTP API를 적는다. 엔드포인트, 메서드, 요청과 응답의 형식, 인증 요구 여부를 기능군 단위로 묶어 정리한다. -->

## 6.2 인증과 토큰 (Authentication and Tokens)

<!-- 액세스 토큰, 리프레시 토큰, 스트림 접근 토큰의 형식과 수명, 발급과 갱신과 폐기의 경로를 적는다. SRS FR-023이 남긴 폐기 지연 문제를 여기서 해소한다. -->

## 6.3 컴포넌트 간 인터페이스 (Inter-component Interface)

<!-- Gateway, Engine, Media가 서로를 호출하는 방식과 규약을 적는다. 외부 API와 달리 내부 규약이므로, 인증을 어떻게 다룰지도 함께 정한다. -->

## 6.4 스트리밍 인터페이스 (Streaming Interface)

<!-- Video Source로부터의 RTSP 수신과 Client App으로의 HLS/WebRTC 전달을 적는다. Client App이 Gateway를 경유하지 않고 Media에 직접 접속하는 경로가 이 절의 중심이다. -->

## 6.5 오류 응답 규약 (Error Response Convention)

<!-- 오류를 어떤 형식으로 돌려줄지 하나의 규약으로 정한다. 상태 코드의 사용 기준과 오류 코드 체계를 정하여 모든 API가 같은 방식을 따르게 한다. -->

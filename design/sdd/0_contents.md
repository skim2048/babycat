# 1. Introduction; 개요
1. Purpose; 목적
2. Document Organization; 문서 구성
3. References; 참조

# 2. Components and Responsibilities; 컴포넌트와 책임

# 3. Interface Design; 인터페이스 설계
1. #1 Client App - API Server
2. #2 API Server - App Server
3. #3 App Server - RTSP Source (조건부: ONVIF PTZ)
4. #4 App Server - MediaMTX Server
5. #5 MediaMTX Server - RTSP Source
6. #6 MediaMTX Server - Client App
7. #7 API Server - Storage
8. #8 App Server - Storage

# 4. Runtime Behavior; 런타임 동작
1. Pipeline Lifecycle; 파이프라인 수명주기
2. Inference and Event Detection; 추론·이벤트 감지
3. Trigger Clip Recording; 트리거 클립 녹화
4. Failure Recovery; 장애 복구

# 5. Data Design; 데이터 설계
1. Clip Path Schema; 클립 경로 스키마
2. Clip Metadata; 클립 메타데이터
3. Database Schema; 데이터베이스 스키마
4. Camera Profile; 카메라 프로필

# 6. Design Decisions; 설계 결정 기록

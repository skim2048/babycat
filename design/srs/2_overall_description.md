# 2. 전체 설명; Overall Description

## 2.1 제품 관점; Product Perspective

babycat은 독립 실행형(standalone) 시스템이다. 외부 클라우드 플랫폼이나 상위
소프트웨어 시스템의 일부로 동작하지 않으며, 엣지 디바이스 위에서 자기 완결적으로
구동된다.

babycat은 세 가지 외부 인터페이스를 가진다.

- **IP 카메라**: RTSP를 통해 H.264 비디오 스트림을 수신한다. babycat은 카메라의
  소비자(consumer)이며, 카메라의 내부 동작에 관여하지 않는다. 카메라가 ONVIF를
  지원하는 경우 PTZ 제어 인터페이스를 추가로 갖는다.
- **클라이언트**: HTTP API를 통해 babycat의 상태를 조회하고 설정을 변경하며
  저장된 클립을 관리한다. 클라이언트의 구현 형태(웹 브라우저, CLI, 모바일 앱 등)는
  babycat의 관심 밖이다.
- **파일시스템**: 이벤트 클립과 설정 파일을 로컬 파일시스템에 영속 저장한다.
  외부 스토리지 서비스(클라우드, NAS 등)는 지원 대상이 아니다.

## 2.2 전체 시스템 구성; Overall System Configuration

## 2.3 전체 동작; Overall Operation

## 2.4 주요 기능; Project Functions

## 2.5 사용자 분류 및 특성; User Classes and Characteristics

## 2.6 가정 및 의존성; Assumptions and Dependencies

## 2.7 요구사항 배분; Apportioning of Requirements

## 2.8 하위 호환성; Backward Compatibility

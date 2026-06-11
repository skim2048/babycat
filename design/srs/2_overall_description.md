# 2. Overall Description; 전체 설명

## 2.1 Product Perspective; 제품 조망

Babycat은 Jetson Board에서 동작하는 독립 실행형 백엔드로서 RTSP Source로부터 비디오 스트림을 수신하여 VLM으로 분석하고 Client App의 요청에 맞는 서비스를 제공한다.

![Product Perspective](figs/2-1_product_perspective.jpg)

|항목|설명|
|---|---|
|Client App|Babycat API를 통해 시스템과 상호작용하는 외부 클라이언트 앱.|
|RTSP Source|RTSP를 통해 비디오 스트림을 Babycat에 송신하는 외부 소스.|

## 2.2 Overall System Configuration; 전체 시스템 구성

Babycat은 네 가지 내부 컴포넌트로 구성된다.

![Overall System Configuration](figs/2-2_overall_system_conf.jpg)

실선 화살표는 상시 연결을, 점선 화살표는 조건부 연결을 나타낸다. Storage 옆의 레이블(rw)은 해당 컴포넌트의 접근 권한을 나타낸다.

|항목|설명|
|---|---|
|MediaMTX Server|RTSP Source로부터 비디오 스트림을 수신하고, App Server 및 Client App에 재배포하는 미디어 서버.|
|API Server|Client App의 HTTP 요청을 처리하는 단일 진입점 서버. App Server와 연동하여 기능을 수행한다.|
|App Server|VLM 추론, 이벤트 감지, 비디오 클립 저장 등 핵심 기능을 담당하는 서버. ONVIF를 지원하는 RTSP Source에 한해 PTZ 제어를 수행한다.|
|Storage|시스템 운영에 필요한 데이터의 영속 저장소. 비디오 클립, 메타데이터, 카메라 프로필 등을 포함한다.|

## 2.3 Overall Operation; 전체 동작 방식

### A. 카메라 프로필 관리

1. **User**가 **Client App**에서 카메라 프로필을 작성한 후 저장을 요청한다.
2. **Client App**은 작성된 내용을 **API Server**에 전송한다.
3. **API Server**는 수신한 내용을 **App Server**에 전달한다.
4. **App Server**는 수신한 내용을 **Storage**에 저장한다.

### B. 카메라 제어

본 시나리오는 카메라 프로필이 저장되어 있고, **RTSP Source**가 ONVIF PTZ를 지원하는 경우에 한한다.

1. **User**가 **Client App**에서 PTZ 방향 버튼을 누른다.
2. **Client App**은 이동 명령을 **API Server**에 전송한다.
3. **API Server**는 이동 명령을 **App Server**에 전달한다.
4. **App Server**는 ONVIF를 통해 **RTSP Source**에 이동 명령을 전달한다.
5. **User**가 버튼에서 손을 떼면 **Client App**은 정지 명령을 **API Server**에 전송한다.
6. **API Server**는 정지 명령을 **App Server**에 전달한다.
7. **App Server**는 ONVIF를 통해 **RTSP Source**에 정지 명령을 전달한다.

### C. 라이브 스트리밍

본 시나리오는 카메라 프로필이 저장되어 있는 경우에 한한다.

1. **User**가 **Client App**에서 라이브 스트리밍 재생을 요청한다.
2. **Client App**은 **API Server**에 스트림 접속 정보를 요청한다.
3. **API Server**는 **MediaMTX Server**의 스트림 접속 정보를 **Client App**에 반환한다.
4. **Client App**은 **MediaMTX Server**에 직접 연결하여 HLS 또는 WebRTC 스트림을 수신한다.

### D. 비디오 분석 및 이벤트 클립 저장

본 시나리오는 카메라 프로필이 저장되어 있는 경우에 한한다.

1. **App Server**는 저장된 카메라 프로필의 소스를 **MediaMTX Server**에 전달하고 파이프라인을 재시작한다.
2. **MediaMTX Server**는 RTSP를 통해 **RTSP Source**로부터 비디오 스트림을 수신하여 **App Server**에 송신한다.
3. **App Server**는 수신한 비디오 스트림에서 주기적으로 프레임을 추출한다.
4. **App Server**는 추출한 프레임을 VLM에 입력하여 장면 설명을 얻는다.
5. **App Server**는 VLM 응답에 사용자가 설정한 이벤트 키워드가 포함되어 있는지 확인한다.
6. 포함되어 있다면 **App Server**는 해당 시점의 비디오 클립을 **Storage**에 저장한다.

### E. 클립 재생

1. **User**가 **Client App**에서 특정 클립의 재생 버튼을 누른다.
2. **Client App**은 **API Server**에 해당 클립을 요청한다.
3. **API Server**는 **Storage**에서 해당 클립 파일을 읽어온 후 **Client App**에 스트리밍한다.
4. **Client App**은 수신한 스트림을 화면에 표시한다.

### F. 클립 조회 및 삭제

1. **User**가 **Client App**에서 클립 목록 조회 또는 삭제 버튼을 누른다.
2. **Client App**은 **API Server**에 클립 목록 조회 또는 삭제를 요청한다.
3. **API Server**는 **Storage**에서 클립 목록을 조회하거나 삭제하고 결과를 **Client App**에 반환한다.
4. **Client App**은 요청 결과를 화면에 표시한다.

## 2.4 Project Functions; 제품 주요 기능

작성 생략

## 2.5 User Classes and Characteristics; 사용자 계층과 특징

### 운영자(Operator)
- 카메라가 설치된 현장을 관리하며 Client App을 통해 Babycat과 상호작용하는 주 사용자이다.
- 카메라 프로필 설정, 라이브 스트림 모니터링, 이벤트 클립 조회 및 삭제를 주로 수행한다.
- VLM이나 AI에 대한 전문 지식 없이도 기본 기능을 사용할 수 있어야 한다.

### 시스템 관리자(System Administrator)
- Jetson Board에 Babycat을 배포하고 유지 관리하는 사람이다.
- Docker 및 Linux에 대한 기본 지식이 요구된다.
- 초기 환경 설정(환경 변수, 네트워크, VLM 모델 선택 등)을 담당한다.

## 2.6 Assumptions and Dependencies; 가정과 종속관계

## 2.7 Apportioning of Requirements; 단계별 요구사항

## 2.8 Backward Compatibility; 하위 호환성

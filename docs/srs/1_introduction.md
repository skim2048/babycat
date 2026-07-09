# 1. 개요 (Introduction)

## 1.1 목적 (Purpose)

- 프로젝트가 반드시 충족해야 할 요구사항을 확정한다.
- 프로젝트의 설계 및 구현 기준이자 근거로 활용한다.
- 각 요구사항과 매칭되는 산출물 및 테스트를 추적한다.

## 1.2 규칙 (Conventions)

### 요구사항

요구사항 본문의 "~해야 한다"는 필수사항을, "~할 수 있다"는 선택사항을 나타낸다.

#### (1) 식별자

요구사항 유형에 따라 식별자를 아래와 같이 표기한다.

|접두어|요구사항 유형|설명|
|---|---|---|
|`FR`|Functional Requirement (기능 요구사항)|시스템이 수행해야 하는 기능|
|`NFR`|Non-Functional Requirement (비기능 요구사항)|성능·신뢰성·보안 등 품질 속성|
|`CON`|Constraint (제약사항)|기술·환경·정책상 변경 불가 내용|
|`IF`|Interface (인터페이스)|외부 시스템과의 인터페이스|

- 표기 형식은 `<접두어>-<세자리 번호>` 이다. (예: `FR-001`, `NFR-002`, `CON-001`)
- 세자리 번호는 유형 내에서 1부터 순서대로 부여한다.
- 한 번 부여된 번호는 요구사항이 삭제되더라도 재사용하지 않는다.

#### (2) 우선순위

요구사항 우선순위(Priority)를 아래와 같이 표기한다.

|표기|설명|
|---|---|
|`P1`|필수 - 해당 버전에서 반드시 구현해야 하며, 별도의 표기가 없는 경우 `P1`로 간주|
|`P2`|중요 - 구현을 권장하나 일정에 따라 조정 가능|
|`P3`|선택 - 차기 버전으로 보류 가능|

### 기타 문서 요소

기타 문서 요소를 아래와 같이 표기한다.

|표기|설명|
|---|---|
|`***이름***`|외부 시스템·내부 컴포넌트·자원의 이름 강조 (예: `***Gateway***`)|
|`그림 N-M`|N은 장, M은 순번 (예: `그림 1-1`)|
|`기능 N-M`|N은 기능군, M은 순번 (예: `기능 1-1`)|

## 1.3 용어 및 약어 (Terms and Abbreviations)

|용어 및 약어|설명|
|---|---|
|VLM (Vision-Language Model)|이미지와 텍스트를 함께 처리하는 멀티모달 언어 모델|
|RTSP (Real-Time Streaming Protocol)|원격으로 미디어 스트림을 실시간 제어하는 프로토콜|
|H.264|대중적인 비디오 압축 코덱(codec) 중 하나|
|HLS (HTTP Live Streaming)|Apple이 개발한, HTTP 기반 비디오 스트리밍 프로토콜|
|WebRTC (Web Real-Time Communication)|브라우저에서 플러그인 없이 실시간 데이터를 송수신하는 프로토콜|
|PTZ (Pan·Tilt·Zoom)|카메라의 수평·수직 회전 및 광학 줌을 제어하는 기능|
|ONVIF (Open Network Video Interface Forum)|네트워크 보안 카메라 장비의 상호운용성을 위한 개방형 표준 프로토콜|
|GStreamer|파이프라인을 기반으로 비디오를 처리하는 멀티미디어 프레임워크|
|MediaMTX|미디어 스트림의 라우팅, 중계, 변환 등을 수행하는 오픈소스 미디어 서버|
|Edge Device|데이터가 발생하는 현장에서 직접 연산·추론을 수행하는 장치|
|Tegra|NVIDIA의 모바일 및 임베디드 기기용 SoC(System-on-Chip) 프로세서 라인업|
|L4T (Linux for Tegra)|NVIDIA가 Jetson Platform용으로 개발한 Ubuntu 기반 운영체제|
|Jetson Module|Tegra SoC, RAM, Storage를 소형 보드에 집적한 SoM(System-on-Module) 제품|
|Jetson Board|NVIDIA Jetson Module과 캐리어 보드로 구성된 하드웨어 유닛|
|Jetson Platform|NVIDIA Jetson 제품군 전체를 아우르는 에코 시스템|
|CUDA|GPU 가속 연산에 사용하는, NVIDIA의 병렬 컴퓨팅 플랫폼 및 프로그래밍 API|
|TensorRT|NVIDIA의 딥러닝 추론 최적화 엔진|
|Jetson JetPack|NVIDIA Jetson Platform용 소프트웨어 개발 키트|
|Docker|컨테이너 이미지의 빌드, 배포, 실행을 관리하는 오픈소스 컨테이너 런타임|
|NVIDIA Container Toolkit|Docker 컨테이너에서 NVIDIA GPU에 접근할 수 있도록 하는 런타임 툴킷|
|Jetson Container|NVIDIA Jetson Platform 전용 Docker 이미지 빌드 시스템 및 사전 빌드 이미지 모음|
|NanoLLM|NVIDIA Jetson에서 VLM/LLM 추론을 위한 최적화 라이브러리|
|JWT (JSON Web Token)|사용자의 로그인 인증 및 권한 확인에 주로 사용하는 웹 표준 토큰|

## 1.4 관련 문서 (Related Documents)

작성 보류

## 1.5 대상 독자 및 읽는 법 (Intended Audience and Reading Suggestions)

### 설계자
  - 시스템의 범위와 구조를 파악하는 데 집중한다.
  - §1.1에서 문서의 목적을, §2.1에서 제품 범위를 확인한 뒤, §2.2와 §2.3에서 시스템 구조·컴포넌트 구성과 전체 동작 방식을 검토한다.
  - 이후 §2.4에서 주요 기능을, §2.7에서 버전별 기능 범위를 확인하고, 4장에서 외부 인터페이스 요구사항을 살펴본다.

### 개발자
  - 구현에 필요한 요구사항을 파악하는 데 집중한다.
  - §1.2에서 요구사항 식별자 체계를 숙지하고, §1.3에서 용어를 확인한 뒤, 3장에서 개발 및 운영 환경을 파악한다.
  - 이후 4장에서 인터페이스 명세를 검토하고, 7장에서 기능 요구사항을 확인한다.

### 엔지니어
  - 시스템 배포 및 운영에 필요한 정보를 파악하는 데 집중한다.
  - 3장에서 운영·배포·개발 환경을 확인하고, 5장에서 성능 요구사항, 6장에서 비기능 요구사항을 검토한다.

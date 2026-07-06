# 1. 개요 (Introduction)

## 1.1 목적 (Purpose)

- 프로젝트가 반드시 충족해야 할 요구사항을 확정한다.
- 설계 및 구현의 기준이자 근거로 활용한다.
- 각 요구사항에 매칭되는 산출물과 테스트를 추적한다.

## 1.2 프로젝트 범위 (Project Scope)

- 프로젝트명은 `Babycat`이다.
- `Babycat`은 어떤 도메인에 VLM 적용 가능 여부를 검토하는 백엔드이다.
- `Babycat`은 키워드 매칭 방식의 이벤트 감지 기능을 제공한다.
- `Babycat`은 이벤트가 감지된 구간을 비디오 클립으로 자동 저장하는 기능을 제공한다.
- `Babycat`은 장기적인 비디오 변화 추이에 대한 요약 및 분석 기능은 제공하지 않는다.
- `Babycat`은 NVIDIA Jetson Board에서 구동되도록 설계되었다.

## 1.3 문서 규칙 (Document Conventions)

### (1) 요구사항 식별자

각 요구사항 유형에 따라 아래와 같은 식별자 체계로 분류한다.

|접두어|유형|설명|
|---|---|---|
|`FR`|Functional Requirement(기능 요구사항)|시스템이 수행해야 하는 기능|
|`NFR`|Non-Functional Requirement(비기능 요구사항)|성능·신뢰성·보안 등 품질 속성|
|`CON`|Constraint(제약사항)|기술·환경·정책상 변경 불가 내용|
|`IF`|Interface(인터페이스)|외부 시스템과의 인터페이스|

식별자 형식은 `<접두어>-<세자리 번호>` 이다. (예: `FR-001`, `NFR-002`, `CON-001`)

- 번호는 유형 내에서 1부터 순서대로 부여한다.
- 한 번 부여된 번호는 요구사항이 삭제되더라도 재사용하지 않는다.
- 요구사항 본문은 "~해야 한다" 형식으로 기술하여 선택 사항("~할 수 있다")과 구분한다.

### (2) 요구사항 우선순위

요구사항의 우선순위를 아래와 같이 표기한다. 별도의 표기가 없는 요구사항은 `P1`로 간주한다.

|표기|의미|
|---|---|
|`P1`|필수. 해당 버전에서 반드시 구현한다.|
|`P2`|중요. 구현을 권장하나 일정에 따라 조정할 수 있다.|
|`P3`|선택. 차기 버전으로 미룰 수 있다.|

### (3) 기타 문서 요소

|표기|유형|설명|
|---|---|---|
|`***이름***`|구성 요소|외부 시스템/요소·내부 컴포넌트·자원의 이름 강조 (예: `***Gateway***`)|
|`그림 N-M`|그림|N은 장, M은 순번 (예: `그림 1-1`)|
|`기능 N-M`|기능|N은 기능군, M은 순번 (예: `기능 1-1`)|

## 1.4 용어 및 약어 (Terms and Abbreviations)

|용어 및 약어|내용|
|---|---|
|VLM|Vision-Language Model. 이미지와 텍스트를 함께 처리하는 멀티모달 언어 모델이다.|
|RTSP|Real-Time Streaming Protocol. 원격으로 미디어 스트림을 제어할 때 사용한다.|
|H.264|대중적인 비디오 압축 코덱(codec) 중 하나이다.|
|HLS|HTTP Live Streaming. Apple이 개발한 HTTP 기반 비디오 스트리밍 프로토콜이다.|
|WebRTC|Web Real-Time Communication. 브라우저에서 플러그인 없이 실시간 데이터를 송수신한다.|
|PTZ|Pan·Tilt·Zoom. 수평·수직 회전 및 광학 줌을 제어하는 카메라 기능이다.|
|ONVIF|Open Network Video Interface Forum. 네트워크 보안 카메라 장비의 상호운용성을 위한 개방형 표준 프로토콜이다.|
|GStreamer|파이프라인 기반 멀티미디어 프레임워크이다. 비디오 디코딩 및 프레임 처리에 사용한다.|
|MediaMTX|오픈소스 미디어 서버이다. 미디어 스트림의 라우팅, 중계, 변환 등을 수행한다.|
|Edge Device|데이터가 발생하는 현장에서 직접 연산·추론을 수행하는 엣지 디바이스이다. 클라우드에 의존하지 않고 로컬에서 처리한다.|
|Tegra|NVIDIA의 모바일 및 임베디드 기기용 SoC(System on Chip) 프로세서 라인업이다.|
|L4T|NVIDIA가 Jetson Platform용으로 개발한 Ubuntu 기반 운영체제(Linux for Tegra)이다.|
|Jetson Module|NVIDIA의 SoM(System-on-Module) 제품으로, Tegra SoC, RAM, Storage를 소형 보드에 집적한 연산 모듈이다. 캐리어 보드 없이는 단독으로 동작할 수 없다.|
|Jetson Board|NVIDIA Jetson Module과 캐리어 보드로 구성된 완전한 하드웨어 유닛이다. Edge Device의 일종이다.|
|Jetson Platform|NVIDIA Jetson 제품군 전체를 아우르는 에코 시스템으로, Jetson Module, Jetson JetPack SDK, 파트너 하드웨어·소프트웨어를 포함하는 엣지 AI 컴퓨팅 환경이다.|
|CUDA|NVIDIA의 병렬 컴퓨팅 플랫폼 및 프로그래밍 API이다. GPU 가속 연산에 사용한다.|
|TensorRT|NVIDIA의 딥러닝 추론 최적화 엔진이다. 모델 양자화 및 최적화를 통해 추론 속도를 향상시킨다.|
|Jetson JetPack|NVIDIA Jetson Platform용 소프트웨어 개발 키트이다. L4T, CUDA, cuDNN, TensorRT를 포함한다.|
|Docker|컨테이너 이미지의 빌드, 배포, 실행을 관리하는 오픈소스 컨테이너 런타임이다.|
|NVIDIA Container Toolkit|Docker 컨테이너에서 NVIDIA GPU에 접근할 수 있도록 하는 런타임 툴킷이다.|
|Jetson Container|NVIDIA Jetson Platform 전용 Docker 이미지 빌드 시스템 및 사전 빌드 이미지 모음이다.|
|NanoLLM|NVIDIA Jetson에서 VLM/LLM 추론을 위한 최적화 라이브러리이다. Jetson Container 이미지 형태로 제공된다.|
|JWT|JSON Web Token. 당사자 간 정보 교환을 안전하게 처리한다.|

## 1.5 관련 문서 (Related Documents)

작성 보류

## 1.6 독자대상과 읽는법 (Intended Audience and Reading Suggestions)

### 설계자
  - 시스템의 범위와 구조를 파악하는 데 집중한다.
  - 1.1과 1.2에서 문서의 목적과 제품 범위를 확인한 뒤, 2.1과 2.2에서 시스템 구조와 컴포넌트 구성을 검토한다.
  - 이후 2.3에서 전체 동작 방식을, 2.7에서 버전별 기능 범위를 확인하고, 4장에서 외부 인터페이스 요구사항을 살펴본다.

### 개발자
  - 구현에 필요한 요구사항을 파악하는 데 집중한다.
  - 1.3에서 요구사항 식별자 체계를 숙지하고, 1.4에서 용어를 확인한 뒤, 3장에서 개발 및 운영 환경을 파악한다.
  - 이후 4장에서 인터페이스 명세를 검토하고, 7장에서 기능 요구사항을 확인한다.

### 엔지니어
  - 시스템 배포 및 운영에 필요한 정보를 파악하는 데 집중한다.
  - 3장에서 운영·배포·개발 환경을 확인하고, 5장에서 성능 요구사항, 6장에서 비기능 요구사항을 검토한다.

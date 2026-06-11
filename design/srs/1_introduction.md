# 1. Introduction; 개요

## 1.1 Purpose; 목표

- 반드시 충족해야 할 요구사항을 설계와 구현에 앞서 확정한다.
- 확정된 요구사항을 설계·구현의 기준이자 검증의 근거로 활용한다.
- 각 요구사항에 식별자를 부여하여 매칭되는 산출물·시험을 추적한다.

## 1.2 Product Scope; 범위

- 프로젝트명은 Babycat이다.
- Babycat은 비디오 분석 기술이 요구되는 분야에 VLM을 도입하기 위한 범용 백엔드이다.
- Babycat은 키워드 매칭 방식의 자동 이벤트 탐지 기능을 제공한다.
- Babycat은 이벤트가 탐지된 구간을 비디오 클립으로 자동 저장하는 기능을 제공한다.
- Babycat은 장기적인 비디오 변화 추이에 대한 요약 및 분석 기능은 제공하지 않는다.
- Babycat은 임베디드 환경을 고려하여 NVIDIA Jetson Board에서 구동되도록 설계되었다.

## 1.3 Document Conventions; 문서 규칙

요구사항을 유형에 따라 아래와 같은 식별자 체계로 분류한다.

|접두어|유형|설명|
|---|---|---|
|`FR`|Functional Requirement(기능 요구사항)|시스템이 수행해야 하는 기능|
|`NFR`|Non-Functional Requirement(비기능 요구사항)|성능·신뢰성·보안 등 품질 속성|
|`CON`|Constraint(제약사항)|기술·환경·정책상 변경 불가 내용|

식별자 형식은 `<접두어>-<세자리 번호>` 이다. (예: `FR-001`, `NFR-002`, `CON-001`)

- 번호는 유형 내에서 1부터 순서대로 부여한다.
- 한 번 부여된 번호는 요구사항이 삭제되더라도 재사용하지 않는다.
- 요구사항 본문은 "~해야 한다"(shall) 형식으로 기술하여 선택 사항("~할 수 있다")과 구분한다.

## 1.4 Terms and Abbreviations; 정의 및 약어

|용어|정의|
|---|---|
|VLM|시각-언어 모델(Vision-Language Model). 이미지와 텍스트를 함께 처리하는 멀티모달 언어 모델.|
|RTSP|실시간 스트리밍 프로토콜(Real-Time Streaming Protocol). IP 카메라 등의 미디어 스트림 제어에 사용.|
|H.264|ITU-T H.264/AVC. 대중적인 비디오 압축 코덱 중 하나.|
|HLS|HTTP 라이브 스트리밍(HTTP Live Streaming). Apple이 개발한 HTTP 기반 적응형 비디오 스트리밍 프로토콜.|
|WebRTC|웹 실시간 통신(Web Real-Time Communication). 브라우저에서 플러그인 없이 실시간 음성·영상·데이터를 전송하는 W3C/IETF 표준.|
|PTZ|팬(Pan), 틸트(Tilt), 줌(Zoom). 수평·수직 회전 및 광학 줌을 제어하는 카메라 기능.|
|ONVIF|개방형 네트워크 비디오 인터페이스 포럼(Open Network Video Interface Forum). 네트워크 보안 카메라 장비의 상호운용성을 위한 개방형 표준 프로토콜로, IP 카메라의 PTZ 제어·스트림 설정 등을 규정.|
|GStreamer|파이프라인 기반 멀티미디어 프레임워크. 비디오 디코딩 및 프레임 처리에 사용.|
|MediaMTX|오픈소스 미디어 서버. 이 프로젝트에서는 RTSP 수신 및 HLS/WebRTC 송신에 사용.|
|Tegra|NVIDIA의 모바일 및 임베디드 기기용 SoC(System on Chip) 프로세서 라인업.|
|L4T|NVIDIA가 Jetson Platform용으로 개발한, Ubuntu 기반 운영체제(Linux for Tegra).|
|Jetson Module|NVIDIA의 SoM(System-on-Module) 제품으로, Tegra SoC, RAM, Storage를 소형 보드에 집적한 연산 모듈. 캐리어 보드 없이 단독 동작 불가.|
|Jetson Board|NVIDIA Jetson Module과 캐리어 보드로 구성된 완전한 하드웨어 유닛.|
|Jetson Platform|NVIDIA Jetson 제품군 전체를 아우르는 에코 시스템. Jetson Module, Jetson JetPack SDK, 파트너 하드웨어·소프트웨어를 포함하는 엣지 AI 컴퓨팅 환경.|
|CUDA|NVIDIA의 병렬 컴퓨팅 플랫폼 및 프로그래밍 API. GPU 가속 연산에 사용.|
|TensorRT|NVIDIA의 딥러닝 추론 최적화 엔진. 모델 양자화 및 최적화를 통해 추론 속도를 향상.|
|Jetson JetPack|NVIDIA Jetson Platform용 소프트웨어 개발 킷(SDK). L4T, CUDA, cuDNN, TensorRT를 포함.|
|Docker|컨테이너 이미지의 빌드, 배포, 실행을 관리하는 오픈소스 컨테이너 런타임.|
|NVIDIA Container Toolkit|Docker 컨테이너에서 NVIDIA GPU에 접근할 수 있도록 하는 런타임 툴킷.|
|Jetson Container|NVIDIA Jetson Platform 전용 Docker 이미지 빌드 시스템 및 사전 빌드 이미지 모음(dustynv/jetson-containers). NanoLLM을 비롯한 다수의 ML 프레임워크 이미지를 제공.|
|NanoLLM|NVIDIA Jetson에서 VLM/LLM 추론을 위한 최적화 라이브러리. Jetson Container 이미지 형태로 제공.|

## 1.5 Related Documents; 관련 문서

작성 보류

## 1.6 Intended Audience and Reading Suggestions; 대상 및 읽는 방법

보충 필요

### 설계자
시스템의 범위와 구조를 파악하는 데 집중한다. 1.1과 1.2에서 문서의 목적과 제품 범위를 확인한 뒤, 2.1과 2.2에서 시스템 구조와 컴포넌트 구성을 검토한다. 이후 2.4에서 주요 기능 목록을 확인하고, Section 4에서 외부 인터페이스 요구사항을 살펴본다.

### 개발자
구현에 필요한 요구사항을 파악하는 데 집중한다. 1.3에서 요구사항 식별자 체계를 숙지하고, 1.4에서 용어를 확인한 뒤, Section 3에서 개발 및 운영 환경을 파악한다. 이후 Section 4에서 인터페이스 명세를 검토하고, Section 7에서 기능 요구사항을 확인한다.

### 엔지니어
시스템 배포 및 운영에 필요한 정보를 파악하는 데 집중한다. Section 3에서 운영·배포·개발 환경을 확인하고, Section 5에서 성능 요구사항, Section 6에서 비기능 요구사항을 검토한다.

## 1.7 Project Output; 프로젝트 산출물

작성 보류


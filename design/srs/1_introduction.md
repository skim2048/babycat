# 1. 개요; Introduction

## 1.1 목표; Purpose

- 본 문서는 이 프로젝트가 반드시 충족해야 할 요구사항을 설계와 구현에 앞서 결정하기 위해 작성되었다.
- 확정된 요구사항은 설계·구현의 기준이자 검증의 근거가 되며, 각 요구사항에 식별자를 부여하여 이후 산출물·시험과 추적 가능하게 매치한다.

## 1.2 프로젝트 범위; Project Scope

- 프로젝트 이름은 babycat이다.
- babycat은 비디오 분석이 요구되는 분야에 VLM(Vision Language Model)을 적용할 수 있는지 빠르게 프로토타이핑 하기 위한 범용 소프트웨어이다.
- babycat은 IP 카메라로부터 RTSP(Real-Time Streaming Protocol)를 통해 송신된 비디오 스트림을 VLM으로 분석하고, 미리 정의된 키워드에 따라 이벤트를 감지하여 이를 비디오 클립으로 저장하는 백엔드이다.
- babycat은 둘 이상의 IP 카메라로부터 동시에 비디오를 수신할 수 없다.
- babycat은 H.264 코덱으로 인코딩된 실시간 스트림만을 비디오 입력 소스로 인식하며, 다른 코덱(H.265/HEVC)이나 비디오 파일 포맷(mp4)은 아직 지원 대상이 아니다.
- babycat은 Jetson Orin NX 급 이상의 단일 NVIDIA 엣지 디바이스에서 구동된다.
- babycat은 하드웨어 디코딩/인코딩을 사용하므로 해당 디코더가 없는 Jetson Orin Nano 급 NVIDIA 엣지 디바이스는 지원 대상이 아니다.
- babycat의 VLM 추론은 외부 클라우드 서비스 연결 없이 로컬에서만 이루어진다.
- babycat은 ONVIF 프로토콜을 통해 PTZ(Pan-Tilt-Zoom) 카메라를 제어할 수 있다.

## 1.3 문서 규약; Document Conventions

본 문서는 요구사항을 유형에 따라 아래와 같은 식별자 체계로 분류한다.

|접두어|유형|설명|
|---|---|---|
|`FR`|Functional Requirement(기능 요구사항)|시스템이 수행해야 하는 기능|
|`NFR`|Non-Functional Requirement(비기능 요구사항)|성능·신뢰성·보안 등 품질 속성|
|`CON`|Constraint(제약사항)|기술·환경·정책상 변경 불가 내용|

식별자 형식은 `<접두어>-<세자리 번호>` 이다. (예: `FR-001`, `NFR-002`, `CON-001`)

- 번호는 유형 내에서 1부터 순서대로 부여한다.
- 한 번 부여된 번호는 요구사항이 삭제되더라도 재사용하지 않는다.
- 요구사항 본문은 "~해야 한다"(shall) 형식으로 기술하여 선택 사항("~할 수 있다")과 구분한다.

## 1.4 용어 및 약어; Terms and Abbreviations

|용어|정의|
|---|---|
|VLM; Vision Language Model|이미지와 텍스트를 함께 처리하는 멀티모달 언어 모델.|
|RTSP; Real-Time Streaming Protocol|IP 카메라가 비디오 스트림을 송출할 때 사용하는 실시간 스트리밍 프로토콜.|
|H.264|ITU-T H.264/AVC. 대중적인 비디오 압축 코덱 중 하나.|
|HLS; HTTP Live Streaming|HTTP 기반 적응형 비디오 스트리밍 프로토콜.|
|PTZ; Pan-Tilt-Zoom|수평·수직 회전 및 광학 줌을 지원하는 카메라 기능.|
|ONVIF; Open Network Video Interface Forum|IP 카메라 및 PTZ 제어를 위한 표준 프로토콜.|
|GStreamer|파이프라인 기반 멀티미디어 프레임워크. 비디오 디코딩 및 프레임 처리에 사용.|
|MediaMTX|오픈소스 미디어 서버. RTSP 스트림 수신 및 HLS/WebRTC 재배포를 담당.|
|Jetson Orin NX|NVIDIA 엣지 AI 모듈. babycat의 최소 사양.|
|엣지 디바이스|NVIDIA 엣지 AI 모듈이 탑재된 컴퓨팅 장치(보드).|
|NanoLLM|Jetson 플랫폼에 최적화된 경량 LLM 추론 라이브러리.|
|이벤트 키워드|사용자가 미리 설정한 문자열. VLM 응답과 비교하여(substring match) 이벤트 발생 여부를 결정하는 기준.|
|비디오 클립|이벤트 발생 시 그 시점을 기준으로 전후 프레임들을 저장한 비디오 파일.|
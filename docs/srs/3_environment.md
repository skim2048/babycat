# 3. 환경 (Environment)

## 3.1 운영 환경 (Operating Environment)

### 하드웨어 환경

최소사양은 모든 기능이 동작하는 사양을, 권장사양은 모든 기능이 원활히 동작하는 사양을 의미한다. 최소사양에서도 기능 누락은 없으나 VLM 추론 주기가 길어진다(§5.4).

|구분|최소|권장|
|---|---|---|
|Jetson Module|Orin NX 16 GB|AGX Orin 64 GB|
|스토리지|NVMe SSD 256 GB|NVMe SSD 512 GB|
|하드웨어 가속|비디오 디코더/인코더 탑재 필수|최소사양과 동일|

비디오 디코더/인코더의 탑재 여부는 Jetson Board에서 장치 노드의 존재로 확인한다.

```bash
ls /dev/v4l2-nvdec /dev/v4l2-nvenc
```

두 노드가 모두 존재해야 하며, 컨테이너에는 docker-compose.yml의 `devices` 설정으로 전달된다.

### 소프트웨어 환경

|항목|버전|비고|
|---|---|---|
|Jetson JetPack|6.2(L4T R36.x)|이외 버전에서의 동작은 보장하지 않는다(§2.6).|
|Docker|29.1.3 (검증 기준)|Docker Compose 플러그인(v5.0.0) 포함.|
|NVIDIA Container Toolkit|1.16.2 (검증 기준)|컨테이너의 GPU 접근에 필수.|

## 3.2 제품 설치 및 설정 (Product Installation and Configuration)

설치 절차는 다음과 같다.

1. GitHub 저장소를 클론한다.
2. `.env.example`을 `.env`로 복사하고 환경 변수를 작성한다.
3. `docker compose up -d --build`로 빌드 및 기동한다.

주요 설정 요소는 다음과 같다.

|설정|위치|설명|
|---|---|---|
|`HOST_IP`|`.env`|Jetson Board의 외부 도달 가능 IP. WebRTC ICE 후보로 광고되며, 미설정 시 외부 노드의 WebRTC 접속이 실패한다.|
|`JWT_SECRET`|`.env`|JWT 서명 비밀키. ***Gateway***와 ***Engine***이 공유한다.|
|`JWT_EXPIRY`, `REFRESH_EXPIRY`|`.env`|액세스/리프레시 토큰 수명(초).|
|`VLM_MODELS`|`.env`|후보 VLM 모델 목록(쉼표 구분). 첫 항목이 부팅 기본값.|
|`MAX_NEW_TOKENS`|`.env`|VLM 추론 1회당 생성 토큰 상한.|
|`DEFAULT_USER`, `DEFAULT_PASS`|`.env`|최초 부팅 시 시드되는 초기 계정.|
|MediaMTX 설정|`config/mediamtx.yml`|미디어 서버 설정 파일.|

설치 시 특기 사항은 다음과 같다.

- 최초 부팅 시 VLM 모델의 MLC 컴파일이 수행되며 모델당 수 분에서 수십 분이 소요된다. 컴파일 결과는 `./data/models`에 캐시되어 이후 부팅에서는 재사용된다.
- 초기 계정은 최초 부팅 시 1회 시드되며, 최초 로그인 시 비밀번호 변경이 요구된다.

## 3.3 배포 환경 (Distribution Environment)

- **마스터 구성**: GitHub 저장소가 마스터이다. 소스코드, Docker 빌드 파일(Dockerfile, docker-compose.yml), 설정 템플릿(`.env.example`, `config/mediamtx.yml`), 설계 문서를 포함한다. 사전 빌드된 이미지 레지스트리는 사용하지 않는다.
- **배포 방법**: 대상 Jetson Board에서 저장소를 클론한 후 현장에서 이미지를 빌드한다. ***Engine***의 베이스 이미지(`dustynv/nano_llm`)는 빌드 시 Docker Hub에서 받아온다.
- **설치 방법**: §3.2를 따른다.
- **패치 및 업데이트 방법**: `git pull` 후 재빌드·재기동한다. 자동 업데이트는 제공하지 않는다.

## 3.4 개발 환경 (Development Environment)

- ***Engine***: Jetson Board 실기가 필수이다. NVIDIA GStreamer 플러그인과 tegra 라이브러리를 호스트에서 바인드 마운트하고 하드웨어 디코더/인코더 장치에 접근하므로 x86 등 다른 환경에서는 구동할 수 없다. 베이스 이미지는 `dustynv/nano_llm:r36.4.0`(Python 3.10)이다.
- ***Gateway***: 일반 PC에서도 개발 가능하다. 베이스 이미지는 `python:3.11-slim`이며 FastAPI 기반이다.
- **개발 도구**: Git, Docker, Python. 그 외 도구는 작성을 보류한다.

## 3.5 테스트 환경 (Test Environment)

- **단위 테스트**: `tests/`의 pytest 스위트로 수행한다. GStreamer 및 하드웨어에 의존하는 테스트는 Jetson 실기에서만 수행 가능하다.
- **성능 벤치마크**: `tests/bench_vlm.py`로 VLM 추론 성능을 측정한다.
- **통합 테스트**: Jetson 실기에서 수행한다. ***Video Source***는 실제 카메라 또는 fakecam으로 구성한다.
- **fakecam**: 사전 녹화된 비디오를 RTSP로 송출하여 ***Video Source***를 대체하는 테스트 도구이다. 동일한 입력을 반복 재현할 수 있어 VLM 프롬프트 및 이벤트 키워드 튜닝에 사용한다.
- 권장사양(AGX Orin) 테스트 환경의 확보 여부는 작성을 보류한다.

## 3.6 형상 관리 (Configuration Management)

- **시스템**: Git, GitHub(`skim2048/babycat`).
- **베이스라인 포함 산출물**: 소스코드, 설계 문서(SRS, 다이어그램), Docker 빌드 파일, 설정 템플릿.
- **형상 관리 제외 대상**: `.env`(비밀키 포함), `data/`(런타임 상태) — 저장소에 포함하지 않는다.
- **브랜치 정책**: `master`를 안정 브랜치로 유지하고, 작업은 별도 브랜치에서 수행 후 병합한다.
- **태깅 정책**: 버전 릴리스 시 `vX.Y` 형식의 태그를 부여한다.

## 3.7 버그트래킹 시스템 (Bugtrack System)

GitHub Issues를 사용한다. 운영 정책(라벨, 템플릿 등)은 작성을 보류한다.

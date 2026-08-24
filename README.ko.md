<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.png">
    <img src="docs/assets/banner-light.png" width="640" alt="Babycat">
  </picture>
</p>

<div align="center">
  <img src="https://img.shields.io/badge/v1.0-2b6e4f" alt="Version">
  <img src="https://img.shields.io/badge/Python-444444" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-444444" alt="FastAPI">
  <img src="https://img.shields.io/badge/GStreamer-444444" alt="GStreamer">
  <img src="https://img.shields.io/badge/Docker-444444" alt="Docker">
  <img src="https://img.shields.io/badge/NanoLLM-444444" alt="NanoLLM">
  <img src="https://img.shields.io/badge/NVIDIA%20Jetson-444444" alt="NVIDIA Jetson">
</div>

<p align="center"><a href="README.md">English</a> · 한국어</p>

Babycat은 NVIDIA Jetson 플랫폼용 VLM 기반 영상 이벤트 감지 백엔드다. 키워드를 지정하면 라이브 영상 소스를 관찰하다가 부합하는 순간을 감지하고, 감지된 구간을 영상 클립으로 저장한다.

- 비전-언어 모델(VLM)로 라이브 RTSP 소스에서 키워드 기반 이벤트를 감지한다.
- 감지된 이벤트 전후 구간을 자동으로 클립으로 녹화하고, 검색 가능한 이벤트 이력을 유지한다.
- NVIDIA Jetson 플랫폼에서 하드웨어 비디오 인코더·디코더와 GPU 추론을 사용해 동작한다.

Babycat은 **백엔드**다. HTTP API를 노출하며 사용자 인터페이스를 포함하지 않는다. 사용 예시로서 참조 클라이언트를 [`client/`](client/) 아래에 제공한다 — 아래 [클라이언트](#클라이언트) 절을 참고한다.

장기 추세 요약과 소리 기반 감지는 범위 밖이다.

## 구조

Babycat은 컴포넌트별 컨테이너 4개로 구성되어 Docker Compose로 조율된다. 외부에는 두 포트만 노출되며, 나머지는 모두 Compose 내부 네트워크에 머문다.

| 컴포넌트 | 컨테이너 | 책임 |
|---|---|---|
| Request router | `router` | 유일한 외부 진입점. 계정·토큰·인증을 담당하고, 모든 요청을 담당 컴포넌트로 중계하며, 모니터링 스트림을 병합한다. |
| Video streamer | `streamer` | 영상 소스(프로필·연결·ONVIF PTZ)를 관리하고, 내장 MediaMTX로 라이브 스트림(HLS/WebRTC)을 재배포한다. |
| Video analyzer | `analyzer` | 스트림에서 프레임을 받아 VLM 추론을 수행하고, 키워드와 대조하여 이벤트 발생 시 recorder에 알린다. |
| Event recorder | `recorder` | 이벤트 클립을 조립하고, 이벤트 이력을 유지하며, 하드웨어·저장소 상태를 보고한다. |

외부 공개 포트는 다음과 같다.

- `8000/tcp` — TLS 종단 게이트웨이(Caddy). 유일한 제어 진입점(HTTPS API)으로, HLS·WebRTC 시그널링 중계를 포함한 모든 요청을 Request router로 전달한다.
- `8189/udp` — Video streamer. WebRTC 미디어/ICE. 저지연을 위해 router를 우회하는 유일한 경로다.

## 요구 사항

Babycat은 NVIDIA Jetson 장비에서 동작한다. 아래 전제 조건은 서로 이어진다 — 보드가 어떤 하드웨어를 갖는지를 정하고, JetPack을 어떻게 플래시했는지가 필요한 소프트웨어의 실제 존재 여부를 정한다.

**1. NVIDIA Jetson 보드.** 최소 사양 보드도 같은 기능을 제공하지만, 자원이 적을수록 실행 가능한 VLM의 선택지가 좁아지고 추론 지연이 커진다.

| | 권장 | 최소 |
|---|---|---|
| Jetson 모듈 | AGX Orin 64 GB | Orin NX 16 GB |
| 저장 장치 | NVMe SSD 512 GB | NVMe SSD 256 GB |

JetPack 6.2.1(L4T R36.x)에서 시험되었다. JetPack 7.x는 GPU 드라이버와 장치 노드 배치가 바뀌었고 추론 스택이 JetPack 6 세대의 CUDA에 의존하므로 지원하지 않는다. 보드는 JetPack 6.x로 플래시한다.

**2. 하드웨어 비디오 인코더·디코더.** Babycat은 NVENC와 NVDEC를 모두 요구한다. 개발 키트는 SKU상 이를 포함하지만, 장치 노드는 JetPack의 멀티미디어 스택이 제공하므로 OS만 플래시한 직후에는 없을 수 있다. 둘 다 존재하는지 확인한다.

```bash
ls /dev/v4l2-nvdec /dev/v4l2-nvenc
```

하나라도 없으면 `sudo apt install nvidia-jetpack`으로 JetPack 전체 구성 요소를 장치에 설치한다.

**3. Docker Engine과 Compose 플러그인.** 공식 [Docker Engine 설치 안내](https://docs.docker.com/engine/install/ubuntu/)를 따른다 — JetPack은 Ubuntu 기반이므로 Ubuntu 지침을 사용한다.

**4. NVIDIA Container Toolkit.** GPU와 하드웨어 코덱을 컨테이너에 노출하기 위해 필요하다. 멀티미디어 스택과 마찬가지로 OS만 플래시한 직후에는 없을 수 있으며, `nvidia-jetpack`에 포함되어 있고 [NVIDIA Container Toolkit 설치 안내](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)에 따라 단독으로도 설치할 수 있다.

이와 별도로 H.264 RTSP 스트림을 제공하는 영상 소스가 필요하다 — IP 카메라, 또는 녹화 영상을 재생하는 대체 소스.

## 시작하기

Babycat은 소스로 배포되며, 이미지는 대상 장치에서 빌드한다.

```bash
# 1. 환경 구성
cp .env.example .env
# .env 편집 — 최소한 HOST_IP, JWT_SECRET, DEFAULT_USER, DEFAULT_PASS, VLM_MODELS

# 2. 빌드와 기동
docker compose build
docker compose up -d
```

최초 기동 시 analyzer가 후보 VLM 모델들을 사전 컴파일하고(모델당 수 분에서 수십 분이 걸리며, 결과는 이후 기동을 위해 캐시된다), 초기 관리자 계정이 생성된다 — 첫 로그인은 비밀번호 변경을 요구한다.

설정은 `.env`로 주입되며, 모든 변수는 [`.env.example`](.env.example)에 문서화되어 있다.

## API

Request router가 `8000` 포트에서 단일 HTTPS API를 노출한다(TLS는 게이트웨이가 종단한다). 인증, 영상 소스 프로필과 PTZ, 클라이언트 데이터 보존, 스트리밍·분석 수명주기, 클립과 이벤트 이력, 병합 모니터링 스트림(SSE)을 다룬다. 전체 경로 지도는 router 서비스([`router/`](router/))를 참고한다.

TLS 인증서는 게이트웨이가 기동할 때 스스로 발급한다 — `.env`의 `HOST_IP`(와 필요 시 `TLS_EXTRA_HOSTS`)를 인증서의 주소로 삼으며, 서명할 사설 CA가 없으면 그것도 함께 만든다. 주소가 바뀌거나 만료가 다가오면 다음 기동에서 재발급하므로 별도 조치가 필요 없다.

접속하는 기기는 CA 루트(`data/caddy/caddy/pki/authorities/local/root.crt`)를 신뢰 저장소에 1회 등록한다. 기기를 여러 대 운용한다면 그 등록을 한 번으로 끝내기 위해 CA를 공유한다 — 첫 기기의 `data/caddy/caddy/pki` 디렉터리를 추가 기기의 같은 경로에 복사해 두면, 그 기기는 기동 시 복사된 CA로 자기 인증서를 발급한다.

## 클라이언트

Babycat은 내장 UI가 없다. API 사용 예시로서 두 참조 클라이언트를 [`client/`](client/) 아래에 제공한다. 이들은 참조 구현으로서 **제품 범위에 속하지 않으며**, 백엔드와 같은 호스트에서든 별도 호스트에서든 독립적으로 기동한다. 백엔드 주소는 각 클라이언트의 로그인 화면에서 입력한다.

**웹 대시보드** ([`client/web`](client/web)) — 데스크톱 브라우저용 Vue 3 대시보드다. 컨테이너가 Vite 개발 서버를 `5173` 포트로 제공한다.

```bash
cd client/web
docker compose up -d
# http://<host>:5173 접속
```

**Android 앱** ([`client/android`](client/android)) — Vue 3 + Capacitor 모바일 앱이다. `5174` 포트의 Vite 개발 서버로 브라우저 미리보기를 할 수 있고, APK 빌드는 Android SDK가 있는 장비에서 수행한다.

```bash
cd client/android
npm install
npm run dev    # http://<host>:5174 에서 브라우저 미리보기
npm run sync   # 웹 자산을 빌드해 android/에 동기화
# 이후 android/를 Android Studio로 열거나: cd android && ./gradlew assembleDebug
```

## 라이선스

Babycat은 [GNU General Public License v3.0](LICENSE)으로 배포된다.

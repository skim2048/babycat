# TLS 인증서 체계와 기기 출고 절차 (PKI Handover)

이 문서는 Babycat 기기를 출고하는 사람이 TLS 인증서와 관련하여 무엇을 어디에서 해야 하는지를 기술한다. 설계상의 결정은 SDD §2.4 (8)·§8.3이, 요구사항은 SRS `NFR-016`이 정하며, 이 문서는 그 결정을 실행하는 절차와 파일, 보관 규칙만 다룬다.

## 1. 용어

|용어|뜻|파일|
|---|---|---|
|CA|인증서에 서명하는 주체|—|
|CA 개인키|CA가 서명할 때 쓰는 비밀 파일. CA만 보유한다|`root.key`|
|CA 인증서|CA의 공개키가 든 인증서. 클라이언트가 서명을 검증할 때 쓰며, 공개해도 무방하다|`root.crt`|
|서버 인증서|gateway의 공개키와 접속 주소(`HOST_IP` 등)가 든 인증서. CA가 서명한다|`data/caddy/site/cert.pem`|
|서버 개인키|gateway가 TLS 통신에 쓰는 개인키|`data/caddy/site/key.pem`|

## 2. 왜 CA가 두 단계인가

보호자 한 명이 펫하우스 여러 대를 폰 한 대로 접속한다. 기기마다 다른 CA가 서버 인증서에 서명하면 폰은 기기 수만큼 CA 인증서를 등록해야 하므로, 폰이 신뢰하는 CA를 제조사 단위로 하나(Root CA)로 고정한다.

그러나 Root CA가 서버 인증서에 직접 서명할 수는 없다. 서버 인증서에는 기기의 접속 주소가 들어가는데, 그 주소는 설치 후에 정해지고 바뀔 수 있으므로 서명은 기기 안에서 기동할 때마다 수행해야 하며, 그러려면 서명에 쓰는 CA 개인키가 기기 안에 있어야 한다. Root CA 개인키를 모든 기기에 복사하면 기기 한 대의 유출이 전 기기에 영향을 미친다. 따라서 Root CA는 기기마다 별도의 CA(Device CA)에 서명하고, 기기는 자기 Device CA 개인키로 자기 서버 인증서에 서명한다.

|CA|보유자|CA 개인키의 위치|CA 인증서의 위치|유효기간|
|---|---|---|---|---|
|Root CA|제조사(사용자 본인)|개발 PC `~/.babycat-ca/root.key`|개발 PC `~/.babycat-ca/root.crt`, mewly 앱 리소스|20년|
|Device CA|기기 1대|그 기기의 `data/caddy/caddy/pki/authorities/local/root.key`|같은 디렉터리의 `root.crt`|10년|

폰(mewly)은 Root CA 인증서만 갖는다. 폰은 Device CA 인증서를 갖고 있지 않으므로, gateway가 서버 인증서를 보낼 때 Device CA 인증서를 함께 보낸다. 그래서 `cert.pem`에는 서버 인증서와 Device CA 인증서가 순서대로 이어져 있다(체인). 폰은 "서버 인증서는 Device CA가 서명했고, Device CA 인증서는 Root CA가 서명했다"를 확인하여 접속을 허용한다.

주의: 기기의 `pki/authorities/local/` 아래 파일명이 `root.crt`·`root.key`인 것은 Caddy의 디렉터리 배치를 그대로 쓰기 때문이며, 내용은 Root CA가 아니라 Device CA의 것이다.

Device CA 인증서에는 서명할 수 있는 주소의 범위를 제한하는 항목(nameConstraints)이 있어, 사설 IPv4 대역(10/8·172.16/12·192.168/16)·127/8·`localhost`·`.local` 밖의 주소가 든 서버 인증서는 클라이언트가 거부한다. 따라서 `.env`의 `HOST_IP`와 `TLS_EXTRA_HOSTS`는 이 범위 안이어야 한다. 이 제한은 Device CA 개인키가 유출되어도 그 기기가 공인 주소의 서버 인증서를 만들 수 없게 하기 위한 것이다.

## 3. 개발 기기와 제품 기기

gateway의 발급 스크립트 `docker/gateway/issue-cert.sh`는 기동 시 `data/caddy/caddy/pki/authorities/local/`에 CA 인증서와 CA 개인키가 있으면 그것으로 서버 인증서에 서명하고, 없으면 그 자리에 자체 CA를 만들어 서명한다. 기기에서 하는 일은 두 경우 모두 `docker compose up -d`이며 차이는 다음과 같다.

|구분|CA 파일이 그 자리에 있는 이유|폰에 필요한 CA 인증서|
|---|---|---|
|제품 기기|출고 전에 Device CA 파일을 복사해 두었다(§4)|mewly에 동봉된 Root CA 인증서. 폰에서 할 일이 없다|
|개발 기기|스크립트가 최초 기동 시 자체 CA를 만들었다|그 기기의 `root.crt`를 폰·브라우저에 1회 설치한다|

mewly는 Root CA 인증서를 동봉하고 사용자 설치 CA 인증서도 신뢰하므로(network security config), 개발 기기의 자체 CA 인증서를 폰에 설치하면 같은 앱으로 접속할 수 있다.

## 4. 출고 절차

명령은 모두 개발 PC에서 `tools/provision-device.sh`로 수행한다. 기기에서는 파일 복사와 `docker compose up -d`만 한다.

### 4.1 Root CA 생성 — 최초 1회

```bash
tools/provision-device.sh init
```

`~/.babycat-ca/`에 Root CA 개인키 `root.key`(0600)와 Root CA 인증서 `root.crt`가 생성된다. 보관 위치를 바꾸려면 `ROOT_DIR` 환경 변수를 지정한다. 이미 있으면 스크립트가 거부한다.

### 4.2 mewly에 Root CA 인증서 동봉 — 최초 1회

`~/.babycat-ca/root.crt`를 mewly 프로젝트의 리소스로 복사하고 앱을 빌드한다. 이후 출고되는 모든 기기는 이 앱으로 접속된다. Root CA를 재생성하면 이 단계를 다시 해야 한다.

### 4.3 Device CA 발급 — 기기 1대마다

```bash
tools/provision-device.sh issue BC-2026-0001
```

- 시리얼 형식은 `BC-<연도>-<일련번호 4자리>`이며, 스크립트가 형식을 검사한다. 같은 시리얼은 두 번 발급할 수 없다.
- 결과는 `provision/BC-2026-0001/`에 생성된다(gitignore 대상).
  - `caddy/pki/authorities/local/root.crt` — Device CA 인증서
  - `caddy/pki/authorities/local/root.key` — Device CA 개인키(0600)
  - `manufacturer-root.crt` — Root CA 인증서 사본(참고용)

### 4.4 기기에 복사 — 기기 1대마다

기기에서 README §Getting Started의 데이터 디렉터리 생성(`mkdir -p data/...`)까지 마친 뒤, `provision/BC-2026-0001/caddy` 디렉터리를 기기의 `data/caddy/` 아래에 복사한다. 복사 후 기기에 다음 두 파일이 있어야 한다.

- `data/caddy/caddy/pki/authorities/local/root.crt`
- `data/caddy/caddy/pki/authorities/local/root.key`

### 4.5 기동 — 기기 1대마다

```bash
docker compose up -d
```

gateway가 4.4의 파일로 서버 인증서에 서명한다. `docker compose logs gateway`에 `issuer=O = Babycat, CN = Babycat Device CA BC-2026-0001`이 보이면 정상이다. 이후 `HOST_IP` 변경과 만료 갱신은 기동 시 자동으로 처리되며 사람이 할 일은 없다.

### 4.6 정리

복사를 마친 `provision/BC-2026-0001/`은 개발 PC에서 삭제한다. Device CA 개인키는 기기 안에만 있어야 한다.

### 4.7 개발 기기를 제품 조건으로 전환

이미 자체 CA로 기동한 기기에서 `data/caddy/caddy/pki`와 `data/caddy/site`를 삭제한 뒤 4.3~4.6을 수행한다. 그 기기의 자체 CA 인증서를 설치해 둔 폰·브라우저에서는 그 항목을 삭제해도 된다.

## 5. 키 보관과 사고 대응

- Root CA 개인키(`~/.babycat-ca/root.key`)는 저장소, 기기, 클라우드 동기화 폴더에 두지 않는다. 분실하면 신규 기기의 Device CA를 발급할 수 없으므로, 오프라인 매체에 백업하고 그 위치를 별도로 기록한다.
- Root CA 개인키가 유출되면 유출자가 임의의 Device CA를 만들 수 있다. 대응은 Root CA 재생성(4.1), mewly 재배포(4.2), 출고된 모든 기기의 Device CA 재발급·재복사(4.7)이며, 이는 전 기기에 대한 조치다.
- Device CA 개인키가 유출되면 유출자가 그 기기 시리얼로 사설 대역 주소의 서버 인증서를 만들 수 있다. 영향은 같은 LAN 안으로 한정된다. 그 기기의 Device CA를 재발급하여 교체하되(4.7), 폐기 목록(CRL)을 배포하는 경로가 없으므로 유출된 Device CA는 만료(10년)까지 유효하다.
- Root CA(20년)와 Device CA(10년)의 만료 전 갱신 절차는 정하지 않았다. 이 문서의 개정 시점에 정한다.

## 6. 관련 파일

|파일|역할|
|---|---|
|`tools/provision-device.sh`|Root CA 생성(`init`), Device CA 발급(`issue`)|
|`docker/gateway/issue-cert.sh`|기기에서 서버 인증서 발급과 체인 생성. CA 파일이 없으면 자체 CA 생성|
|`docker/gateway/entrypoint.sh`|기동 시 발급·갱신 필요 판정|
|`docker/gateway/Caddyfile`|`cert.pem`·`key.pem`으로 TLS 종단|
|`.gitignore`|`provision/`·`data/` 제외|

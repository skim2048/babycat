# TLS 인증서 체계와 기기 프로비저닝 (PKI Handover)

이 문서는 Babycat의 TLS 인증서 체계와, 펫하우스 기기를 출고할 때 수행하는 인증서 프로비저닝 절차를 인수인계 목적으로 기술한다. 설계상의 위치는 SDD §2.4 (8)·§8.3, 요구사항은 SRS `NFR-016`이 정하며, 이 문서는 그 결정을 실행하는 사람이 알아야 할 절차·파일·보관 규칙만 다룬다.

## 1. 배경

펫하우스에는 카메라와 Jetson 보드가 1대씩 설치되고 Babycat은 그 보드에서 구동된다. 보호자는 Android 앱(mewly)으로 접속하며, 보호자 한 명이 반려견 여러 마리를 기르면 펫하우스도 여럿이 된다. 기기마다 다른 CA가 인증서를 서명하면 앱은 CA마다 신뢰 등록을 해야 하므로, 앱이 신뢰하는 CA를 제조사 단위로 하나로 고정하고 기기는 그 아래에서 자기 인증서를 발급하도록 한다.

## 2. 인증서 계층

|단계|주체|보관 위치|유효기간|역할|
|---|---|---|---|---|
|Root CA|제조사(개발 PC)|`~/.babycat-ca/root.{crt,key}` (저장소 밖)|20년|Device CA 발급. 인증서(공개)는 mewly에 동봉|
|Device CA|기기 1대|기기의 `data/caddy/caddy/pki/authorities/local/root.{crt,key}`|10년|출고 시 탑재. 서빙 인증서 서명|
|서빙 인증서|기기(gateway 컨테이너)|기기의 `data/caddy/site/{cert,key}.pem`|820일|기동 시 `HOST_IP` 등을 SAN으로 자동 발급·갱신|

Device CA 파일명이 `root.*`인 것은 Caddy의 pki 디렉터리 배치를 그대로 쓰기 때문이며, 내용은 Root CA가 아니라 Device CA다. `cert.pem`은 서빙 인증서와 Device CA를 이어 붙인 체인이다. 클라이언트는 Device CA를 알지 못하고 Root CA만 신뢰하므로, 체인이 없으면 접속이 실패한다.

Device CA에는 `nameConstraints`가 있어 사설 IPv4 대역(10/8·172.16/12·192.168/16)·127/8·`localhost`·`.local` 밖의 주소에 대한 인증서는 클라이언트가 거부한다. 따라서 `.env`의 `HOST_IP`와 `TLS_EXTRA_HOSTS`는 이 범위 안이어야 한다. 이 제약은 Device CA의 키가 유출되어도 그 기기가 공인 주소의 인증서를 만들 수 없게 하기 위한 것이다.

## 3. 개발 기기와 제품 기기

gateway의 발급 스크립트(`docker/gateway/issue-cert.sh`)는 `pki/authorities/local/`에 CA 파일이 있으면 그것으로 서명하고, 없으면 자체 root CA를 생성한다. 두 경우의 차이는 다음과 같다.

|구분|CA 파일의 출처|클라이언트가 신뢰할 인증서|
|---|---|---|
|제품 기기|출고 시 프로비저닝으로 탑재한 Device CA|mewly에 동봉된 Root CA (설치 작업 없음)|
|개발 기기|최초 기동 시 스크립트가 생성한 자체 CA|그 기기의 `root.crt`를 폰·브라우저에 1회 설치|

mewly는 Root CA를 동봉하는 동시에 사용자 설치 CA도 신뢰하므로(network security config), 개발 기기의 자체 CA를 폰에 설치하면 제품과 같은 앱으로 접속할 수 있다.

## 4. 프로비저닝 절차

모든 작업은 개발 PC에서 `tools/provision-device.sh`로 수행한다. 기기에서는 아무것도 실행하지 않는다.

### 4.1 Root CA 생성 (최초 1회)

```bash
tools/provision-device.sh init
```

`~/.babycat-ca/`에 `root.key`(0600)와 `root.crt`를 만든다. `root.crt`는 mewly 저장소의 리소스로 옮겨 앱에 동봉한다. 보관 위치를 바꾸려면 `ROOT_DIR` 환경 변수를 지정한다.

### 4.2 기기별 Device CA 발급 (기기 1대마다)

```bash
tools/provision-device.sh issue BC-2026-0001
```

- 시리얼 형식은 `BC-<연도>-<일련번호 4자리>`이며, 스크립트가 형식을 검사한다. 같은 시리얼은 두 번 발급할 수 없다.
- 결과는 `provision/BC-2026-0001/` 아래에 놓이며(gitignore 대상), 구조는 다음과 같다.
  - `caddy/pki/authorities/local/root.crt` — Device CA 인증서
  - `caddy/pki/authorities/local/root.key` — Device CA 개인키(0600)
  - `manufacturer-root.crt` — 참고용 Root CA 인증서 사본

### 4.3 기기 탑재

기기의 저장소를 준비하는 단계(README §Getting Started의 `mkdir -p data/...`)에서 `provision/<시리얼>/caddy`를 기기의 `data/caddy/` 아래에 복사한다. 결과 경로는 `data/caddy/caddy/pki/authorities/local/root.{crt,key}`이어야 한다. 이후 `docker compose up -d`로 최초 기동하면 gateway가 이 CA로 서빙 인증서를 발급한다. 기동 로그의 `issuer=`가 `Babycat Device CA <시리얼>`이면 탑재가 올바르다.

`provision/<시리얼>/`은 탑재를 마친 뒤 삭제한다. Device CA 개인키는 기기 안에만 존재해야 한다.

### 4.4 이미 개발용 CA로 기동한 기기를 제품으로 전환

`data/caddy/caddy/pki`와 `data/caddy/site`를 지운 뒤 4.3을 수행한다. 이때 그 기기의 자체 CA를 설치해 둔 클라이언트는 더 이상 그 등록이 필요하지 않다.

## 5. 키 보관과 사고 대응

- Root CA 개인키는 저장소·기기·클라우드 동기화 폴더에 두지 않는다. 분실하면 신규 기기를 출고할 수 없으므로, 오프라인 매체에 백업하고 그 위치를 별도로 기록한다.
- Root CA 개인키가 유출되면 유출자가 임의 기기의 Device CA를 만들 수 있다. 이 경우 Root CA를 재생성하고, mewly를 새 Root CA로 업데이트하며, 출고된 모든 기기의 Device CA를 재발급·재탑재해야 한다. 재발급 절차가 없으므로 이 사고는 전수 회수에 해당한다.
- Device CA 개인키가 유출되면 그 기기 시리얼로 사설 대역의 인증서를 위조할 수 있다. 영향은 같은 LAN 안으로 한정된다. 그 기기의 Device CA를 재발급하여 교체하되(4.4), 현재 폐기 목록(CRL) 배포 경로가 없으므로 유출된 CA는 만료까지 유효하다.
- Root CA(20년)·Device CA(10년)의 만료는 mewly 업데이트와 기기 재프로비저닝으로 처리한다. 만료 전 갱신 절차는 이 문서의 개정 시점에 정한다.

## 6. 관련 파일

|파일|역할|
|---|---|
|`tools/provision-device.sh`|Root CA 생성, Device CA 발급|
|`docker/gateway/issue-cert.sh`|기기에서 서빙 인증서 발급(체인 생성 포함), CA 부재 시 개발용 CA 생성|
|`docker/gateway/entrypoint.sh`|기동 시 발급·갱신 필요 판정|
|`docker/gateway/Caddyfile`|`cert.pem`·`key.pem`으로 TLS 종단|
|`.gitignore`|`provision/`·`data/` 제외|

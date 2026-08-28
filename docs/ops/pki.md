# TLS 인증서 체계와 젯슨 보드 출고 절차

이 문서는 Babycat이 구동되는 젯슨 보드를 출고하는 사람이 TLS 인증서와 관련하여 어디에서 무엇을 해야 하는지를 기술한다. 등장하는 컴퓨터는 두 대다.

- **개발 PC**: Root CA 개인키를 보관하는 유일한 컴퓨터. 이 문서의 명령은 `~/projects/babycat`에서 실행하는 것으로 적는다.
- **젯슨 보드**: 펫하우스에 설치되어 Babycat을 구동하는 보드.

개발 중에는 한 대의 젯슨 보드가 두 역할을 겸할 수 있으며, 그 경우 "개발 PC → 젯슨 보드 복사"는 같은 컴퓨터 안의 `cp`가 된다.

## 1. 용어

|용어|뜻|파일|
|---|---|---|
|CA|인증서에 서명하는 주체|—|
|CA 개인키|CA가 서명할 때 쓰는 비밀 파일. CA만 보유한다|`root.key`|
|CA 인증서|CA의 공개키가 든 인증서. 클라이언트가 서명을 검증할 때 쓰며, 공개해도 무방하다|`root.crt`|
|서버 인증서|gateway의 공개키와 접속 주소(`HOST_IP` 등)가 든 인증서. CA가 서명한다|`data/caddy/site/cert.pem`|
|서버 개인키|gateway가 TLS 통신에 쓰는 개인키|`data/caddy/site/key.pem`|

CA를 생성하면 키 쌍이 생성되는데, 각 키는 서로 다른 파일에 들어간다. 개인키는 `root.key`에, 공개키는 주체·서명과 함께 `root.crt`에 들어간다.

## 2. CA의 구성

보호자 한 명이 펫하우스 여러 대를 폰 한 대로 접속한다. 젯슨 보드마다 다른 CA가 서버 인증서에 서명하면 폰은 보드 수만큼 CA 인증서를 등록해야 하므로, 폰이 신뢰하는 CA를 제조사 단위로 하나(Root CA)로 고정한다.

그러나 Root CA가 서버 인증서에 직접 서명할 수는 없다. 서버 인증서에는 보드의 접속 주소가 들어가는데 그 주소는 설치 후에 정해지고 바뀔 수 있으므로, 서명은 보드 안에서 기동할 때마다 수행해야 하고, 그러려면 서명에 쓰는 CA 개인키가 보드 안에 있어야 한다. Root CA 개인키를 모든 보드에 복사하면 보드 한 대의 유출이 전 보드에 미친다. 따라서 Root CA는 보드마다 별도의 CA(Device CA)에 서명하고, 보드는 자기 Device CA 개인키로 자기 서버 인증서에 서명한다.

|CA|보유자|CA 개인키의 위치|CA 인증서의 위치|유효기간|
|---|---|---|---|---|
|Root CA|제조사|개발 PC `~/.babycat-ca/root.key`|개발 PC `~/.babycat-ca/root.crt`, mewly 앱 리소스, 브라우저를 쓰는 PC의 신뢰 저장소|20년|
|Device CA|젯슨 보드 1대|그 보드의 `data/caddy/caddy/pki/authorities/local/root.key`|같은 디렉터리의 `root.crt`|10년|

클라이언트(폰·브라우저)는 Root CA 인증서만 갖는다. 클라이언트는 Device CA 인증서를 갖고 있지 않으므로 gateway가 서버 인증서를 보낼 때 Device CA 인증서를 함께 보낸다. 그래서 `cert.pem`에는 서버 인증서와 Device CA 인증서가 순서대로 이어져 있다. 클라이언트는 "서버 인증서는 Device CA가 서명했고, Device CA 인증서는 Root CA가 서명했다"를 확인하여 접속을 허용한다.

주의: 보드의 `pki/authorities/local/` 아래 파일명이 `root.crt`·`root.key`인 것은 Caddy의 디렉터리 배치를 그대로 쓰기 때문이며, 내용은 Root CA가 아니라 Device CA의 것이다.

Device CA 인증서에는 서명할 수 있는 주소의 범위를 제한하는 항목(nameConstraints)이 있어, 사설 IPv4 대역(10/8·172.16/12·192.168/16)·127/8·`localhost`·`.local` 밖의 주소가 든 서버 인증서는 클라이언트가 거부한다. 따라서 `.env`의 `HOST_IP`와 `TLS_EXTRA_HOSTS`는 이 범위 안이어야 한다. 이 제한은 Device CA 개인키가 유출되어도 그 보드가 공인 주소의 서버 인증서를 만들 수 없게 하기 위한 것이다.

## 3. 개발 보드와 제품 보드

gateway의 발급 스크립트 `docker/gateway/issue-cert.sh`는 기동 시 `data/caddy/caddy/pki/authorities/local/`에 CA 인증서와 CA 개인키가 있으면 그것으로 서버 인증서에 서명하고, 없으면 그 자리에 자체 CA를 만들어 서명한다. 보드에서 하는 일은 두 경우 모두 `docker compose up -d`이며 차이는 다음과 같다.

|구분|CA 파일이 그 자리에 있는 이유|클라이언트에 필요한 CA 인증서|
|---|---|---|
|제품 보드|출고 전에 Device CA 파일을 복사해 두었다(§4의 5단계)|mewly에 동봉된 Root CA 인증서. 폰에서 할 일이 없다|
|개발 보드|스크립트가 최초 기동 시 자체 CA를 만들었다|그 보드의 `root.crt`를 폰·브라우저에 1회 설치한다|

mewly는 Root CA 인증서를 동봉하고 사용자가 설치한 CA 인증서도 신뢰하므로, 개발 보드의 자체 CA 인증서를 폰에 설치하면 같은 앱으로 접속할 수 있다.

## 4. 출고 절차

|단계|내용|어디에서|횟수|
|---|---|---|---|
|1|Root CA 생성|개발 PC|1회|
|2|mewly에 Root CA 인증서 동봉|개발 PC → mewly 저장소|1회|
|3|Device CA 발급|개발 PC|보드마다|
|4|Babycat 설치 준비|젯슨 보드|보드마다|
|5|Device CA 파일 복사|개발 PC → 젯슨 보드|보드마다|
|6|기동과 확인|젯슨 보드|보드마다|
|7|발급 결과 삭제|개발 PC|보드마다|

### 4.1 Root CA 생성

```bash
tools/provision-device.sh init
ls -l ~/.babycat-ca/
```

`~/.babycat-ca/`에 `root.key`(권한 600)와 `root.crt`가 생성된다. 이미 있으면 스크립트가 거부한다. 보관 위치를 바꾸려면 `ROOT_DIR` 환경 변수를 지정한다. 이 단계는 이후 보드를 몇 대 만들든 다시 하지 않는다.

### 4.2 mewly에 Root CA 인증서 동봉

```bash
tools/cp-rootcrt.sh ~/projects/mewly
```

`~/.babycat-ca/root.crt`가 `<mewly>/android/app/src/main/res/raw/babycat_ca.crt`로 복사된다. 출력의 `subject=`가 `Babycat Root CA`인지 확인한 뒤 mewly 앱을 빌드한다. 이 파일은 공개 파일이므로 mewly 저장소에 커밋해도 무방하다. Root CA를 재생성하지 않는 한 이 파일은 바뀌지 않으며, 재생성했다면 반드시 다시 복사한다.

### 4.3 Device CA 발급

```bash
tools/provision-device.sh issue BC-2026-00000001
find provision -type f
```

시리얼 형식은 `BC-<연도 4자리>-<일련번호 8자리>`이며, 스크립트가 형식을 검사한다. 같은 시리얼은 `provision/` 아래에 결과가 남아 있는 동안 두 번 발급할 수 없다. 결과는 `provision/BC-2026-00000001/`에 생성된다(`.gitignore` 대상).

- `caddy/pki/authorities/local/root.crt` — Device CA 인증서
- `caddy/pki/authorities/local/root.key` — Device CA 개인키(권한 600)
- `manufacturer-root.crt` — Root CA 인증서 사본(참고용)

### 4.4 Babycat 설치 준비

젯슨 보드에서 README의 Getting Started와 같이 진행하되, `docker compose up` 전에 멈춘다.

```bash
git clone <babycat 저장소 주소> babycat
cd babycat
cp .env.example .env
# .env 편집: HOST_IP, DEFAULT_USER, DEFAULT_PASS (VLM_MODELS는 기본값 사용 가능)
mkdir -p data/db/router data/db/recorder data/models data/state/analyzer data/state/recorder data/clips data/caddy
```

새로 플래시한 보드에서는 그 전에 Docker 권한을 갖추어야 한다. 사용자가 `docker` 그룹에 없으면 `docker compose`가 `permission denied while trying to connect to the docker API`로 실패한다.

```bash
sudo usermod -aG docker $USER
newgrp docker        # 또는 로그아웃 후 재로그인
docker ps            # 오류 없이 빈 목록이 나오면 정상
```

보드의 JetPack은 6.2.1(L4T R36.4.x)이어야 한다(`head -1 /etc/nv_tegra_release`). 6.2.2(R36.5)는 동작하지 않는다. 플래시 기본 구성에는 NVIDIA GStreamer 플러그인이 없으므로 JetPack 구성 요소 전체를 설치한다. `apt update`를 먼저 하지 않으면 NVIDIA 저장소 목록이 없어 패키지를 찾지 못한다.

```bash
sudo apt update && sudo apt install nvidia-jetpack
sudo reboot
```

그 밖의 호스트 준비 상태는 6단계의 `docker compose up`이 `preflight` 검사로 확인하여 부족한 항목과 조치를 로그에 남긴다.

`mkdir`를 미리 하는 이유는 소유자다. Docker가 없는 디렉터리를 만들면 root 소유가 되어 이후 `data/` 아래의 파일 작업(5단계의 복사, 클립 정리 등)에 `sudo`가 필요해진다.

### 4.5 Device CA 파일 복사

3단계의 `provision/BC-2026-00000001/caddy` 디렉터리를 보드의 `babycat/data/caddy/` 아래에 복사한다.

```bash
# 개발 PC와 보드가 다른 컴퓨터일 때
scp -r provision/BC-2026-00000001/caddy <사용자>@<보드 IP>:~/babycat/data/caddy/
# 같은 컴퓨터일 때
cp -r provision/BC-2026-00000001/caddy data/caddy/
```

복사 후 보드에 다음 두 파일이 있어야 한다.

- `data/caddy/caddy/pki/authorities/local/root.crt`
- `data/caddy/caddy/pki/authorities/local/root.key`

### 4.6 기동과 확인

```bash
docker compose build
docker compose up -d
docker compose logs preflight   # "모든 검사 통과"가 아니면 표시된 조치 후 up을 다시 실행한다
docker compose logs gateway
```

로그에 `issuer=O = Babycat, CN = Babycat Device CA BC-2026-00000001`이 보이면 정상이다. 다음 명령으로 체인을 검증할 수도 있다.

```bash
echo | openssl s_client -connect <HOST_IP>:8000 -CAfile ~/.babycat-ca/root.crt 2>/dev/null | grep 'Verify return code'
# Verify return code: 0 (ok)
```

이후 `HOST_IP`가 바뀌거나 서버 인증서 만료가 가까워지면 다음 기동 때 gateway가 스스로 재발급한다.

### 4.7 발급 결과 삭제

```bash
rm -r provision/BC-2026-00000001
```

Device CA 개인키는 보드 안에만 있어야 한다. 새 보드를 준비할 때 기존 보드의 `data/caddy/`를 복사하지 않는다 — 그 안의 Device CA는 기존 보드의 것이며, 두 보드가 Device CA를 공유하면 보드마다 CA를 나눈 의미가 없어진다. 새 보드에는 3단계에서 새 시리얼로 발급한 것만 넣는다. 보드의 `data/caddy/`를 잃었을 때는 지운 파일을 되살리지 않고 3·5·6단계를 다시 수행한다. 클라이언트는 Root CA 인증서만 신뢰하므로 Device CA가 바뀌어도 클라이언트에서 할 일은 없다.

### 4.8 개발 보드를 제품 조건으로 전환

이미 자체 CA로 기동한 보드에서 `data/caddy/caddy/pki`와 `data/caddy/site`를 삭제한 뒤 3·5·6·7단계를 수행한다. 그 보드의 자체 CA 인증서를 설치해 둔 클라이언트에서는 그 항목을 삭제해도 된다.

## 5. 브라우저로 접속할 때

웹 클라이언트(Vue dev 서버 등)는 브라우저가 `https://<HOST_IP>:8000`으로 요청을 보내므로, 브라우저를 실행하는 PC가 Root CA 인증서를 신뢰해야 한다. mewly에 동봉한 파일은 Android 앱에만 적용된다. `~/.babycat-ca/root.crt`(또는 mewly의 `babycat_ca.crt`, 같은 파일)를 그 PC에 설치한다.

|환경|방법|
|---|---|
|Windows (Chrome·Edge)|파일을 열어 인증서 설치 → "신뢰할 수 있는 루트 인증 기관" 저장소를 지정한다|
|Windows (Firefox)|Firefox는 Windows 신뢰 저장소를 기본으로 읽지 않는다. `about:config`에서 `security.enterprise_roots.enabled`를 `true`로 바꾸거나, 설정 → 인증서 보기 → 인증 기관 → 가져오기로 직접 넣는다|
|macOS|키체인 접근에 추가하고 "항상 신뢰"로 설정한다. Firefox는 위와 같이 별도로 가져온다|
|Ubuntu|Chrome·Firefox 각각의 설정 → 인증서 관리 → 인증 기관 → 가져오기|

설치 대화 상자의 주체가 `Babycat Root CA`인지 확인한다. 이전 자체 CA 인증서(`Caddy Local Authority - …`)가 남아 있으면 삭제해도 된다.

설치 후 `https://<HOST_IP>:8000/health`를 새 창에서 열어 경고 없이 `status: ok`가 나오면 정상이다. 경고 화면에서 "계속"을 선택하면 브라우저가 그 서버에 대한 예외를 기억하여 이후 요청이 통과하지만, 이는 검증을 건너뛰는 것이므로 설치를 대신하지 않는다.

## 6. 키 보관과 사고 대응

- Root CA 개인키(`~/.babycat-ca/root.key`)는 저장소, 보드, 클라우드 동기화 폴더에 두지 않는다. 분실하면 신규 보드의 Device CA를 발급할 수 없으므로 오프라인 매체에 백업하고 그 위치를 별도로 기록한다.
- Root CA 개인키가 유출되면 유출자가 임의의 Device CA를 만들 수 있다. 대응은 Root CA 재생성(4.1), mewly 재배포(4.2), 출고된 모든 보드의 Device CA 재발급·재복사(4.8)이며, 이는 전 보드에 대한 조치다.
- Device CA 개인키가 유출되면 유출자가 그 보드 시리얼로 사설 대역 주소의 서버 인증서를 만들 수 있다. 영향은 같은 LAN 안으로 한정된다. 그 보드의 Device CA를 재발급하여 교체하되(4.8), 폐기 목록(CRL)을 배포하는 경로가 없으므로 유출된 Device CA는 만료(10년)까지 유효하다.
- Root CA(20년)와 Device CA(10년)의 만료 전 갱신 절차는 정하지 않았다. 이 문서의 개정 시점에 정한다.

## 7. 관련 파일

|파일|역할|
|---|---|
|`tools/provision-device.sh`|Root CA 생성(`init`), Device CA 발급(`issue`)|
|`tools/cp-rootcrt.sh`|Root CA 인증서를 mewly 리소스로 복사|
|`docker/gateway/issue-cert.sh`|보드에서 서버 인증서 발급과 체인 생성. CA 파일이 없으면 자체 CA 생성|
|`docker/gateway/entrypoint.sh`|기동 시 발급·갱신 필요 판정|
|`docker/gateway/Caddyfile`|`cert.pem`·`key.pem`으로 TLS 종단|
|`.gitignore`|`provision/`·`data/` 제외|

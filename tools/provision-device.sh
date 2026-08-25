#!/bin/sh
# 기기 프로비저닝 — 제조사 Root CA로 기기별 Device CA를 발급한다.
# 개발 PC에서 출고 전에 실행하며, 게이트웨이 컨테이너 안에서는 쓰지 않는다.
# 절차와 키 보관 규칙은 docs/ops/pki.md에 있다.
#
# 사용법:
#   tools/provision-device.sh init                 Root CA 생성(최초 1회)
#   tools/provision-device.sh issue <시리얼>        Device CA 발급 → provision/<시리얼>/
#
# 환경 변수:
#   ROOT_DIR  Root CA 보관 디렉터리(기본 ~/.babycat-ca). 저장소 밖에 둔다.
#   OUT_DIR   발급 결과의 상위 디렉터리(기본 ./provision, gitignore 대상)
set -eu

ROOT_DIR="${ROOT_DIR:-$HOME/.babycat-ca}"
OUT_DIR="${OUT_DIR:-$(dirname "$0")/../provision}"
ROOT_DAYS=7300    # Root CA 20년 — 갱신은 mewly 업데이트로 배포되므로 길게 둔다
DEVICE_DAYS=3650  # Device CA 10년 — 펫하우스 기기의 수명 이상
CURVE=P-256

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

init_root() {
  if [ -f "$ROOT_DIR/root.key" ]; then
    echo "Root CA가 이미 있다: $ROOT_DIR/root.key" >&2; exit 1
  fi
  mkdir -p "$ROOT_DIR"; chmod 700 "$ROOT_DIR"
  openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:$CURVE -nodes \
    -keyout "$ROOT_DIR/root.key" -out "$ROOT_DIR/root.crt" -days "$ROOT_DAYS" \
    -subj "/O=Babycat/CN=Babycat Root CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  chmod 600 "$ROOT_DIR/root.key"
  echo "Root CA를 생성했다. 개인키를 백업하고 저장소 밖에 보관한다: $ROOT_DIR"
  echo "mewly에 동봉할 루트 인증서: $ROOT_DIR/root.crt"
}

issue_device() {
  serial="${1:?시리얼이 필요하다 (예: BC-2026-00000001)}"
  case "$serial" in
    BC-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
    *) echo "시리얼 형식은 BC-<연도>-<일련번호 8자리>이다: $serial" >&2; exit 1 ;;
  esac
  [ -f "$ROOT_DIR/root.key" ] || { echo "Root CA가 없다. 먼저 init을 실행한다: $ROOT_DIR" >&2; exit 1; }

  # 게이트웨이가 읽는 경로(issue-cert.sh의 PKI)와 같은 배치로 출력한다.
  # 파일명 root.crt/root.key는 Caddy의 pki 배치를 따른 것이며, 내용은 Device CA다.
  dest="$OUT_DIR/$serial/caddy/pki/authorities/local"
  if [ -e "$dest/root.key" ]; then
    echo "이미 발급된 시리얼이다: $dest" >&2; exit 1
  fi
  mkdir -p "$dest"

  # nameConstraints — 유출된 Device CA가 사설 주소 밖의 인증서를 만들 수 없게 한다.
  # 서빙 인증서의 SAN(HOST_IP·TLS_EXTRA_HOSTS)은 이 범위 안이어야 한다.
  openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:$CURVE -nodes \
    -keyout "$dest/root.key" -subj "/O=Babycat/CN=Babycat Device CA $serial" 2>/dev/null |
  openssl x509 -req -CA "$ROOT_DIR/root.crt" -CAkey "$ROOT_DIR/root.key" \
    -days "$DEVICE_DAYS" -set_serial "0x$(openssl rand -hex 8)" \
    -extfile /dev/fd/3 3<<EXT -out "$dest/root.crt"
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
nameConstraints = critical, permitted;IP:10.0.0.0/255.0.0.0, permitted;IP:172.16.0.0/255.240.0.0, permitted;IP:192.168.0.0/255.255.0.0, permitted;IP:127.0.0.0/255.0.0.0, permitted;DNS:localhost, permitted;DNS:.local
EXT
  chmod 600 "$dest/root.key"
  cp "$ROOT_DIR/root.crt" "$OUT_DIR/$serial/manufacturer-root.crt"
  echo "Device CA를 발급했다: $dest/root.crt"
  echo "기기의 data/caddy/ 아래에 $OUT_DIR/$serial/caddy 를 복사한 뒤 최초 기동한다."
}

case "${1:-}" in
  init) init_root ;;
  issue) shift; issue_device "$@" ;;
  *) usage ;;
esac

#!/bin/sh
# 게이트웨이 서빙 인증서 발급. 평시에는 게이트웨이가 기동 시 스스로 호출하므로
# (entrypoint.sh) 운영자가 직접 실행할 일이 없다.
#
# 운용 모델: CA는 보호자(설치 소유자) 단위로 하나이고, 펫하우스(babycat 기기)가
# 늘 때마다 그 기기의 인증서만 발급한다. 클라이언트(폰·브라우저)는 보호자 CA
# 하나만 신뢰하면 되므로 기기가 늘어도 재설정이 없다.
# - 첫 기기: CA가 없으면 이 스크립트가 생성한다.
# - 추가 기기: 첫 기기의 data/caddy/caddy/pki를 복사해 두면 그 CA로 서명한다.
#
# 인증서는 모든 접속 호스트를 SAN에 담은 단일 파일이다 — IP로 접속하는
# 브라우저는 SNI를 보내지 않아 이름별 인증서 선택이 동작하지 않기 때문이다.
#
# 환경 변수: HOSTS(필수, 공백 구분), CADDY_DATA(caddy 데이터 루트, 기본 /data/caddy)
set -eu

HOSTS="${HOSTS:?접속 호스트 목록이 필요하다 (예: HOSTS=\"192.168.1.10 localhost\")}"
CADDY_DATA="${CADDY_DATA:-/data/caddy}"
DAYS=820     # 서빙 인증서 — macOS·iOS의 상한(825일) 이내
CA_DAYS=3650 # 보호자 CA 루트

PKI="$CADDY_DATA/caddy/pki/authorities/local"
OUT="$CADDY_DATA/site"
mkdir -p "$PKI" "$OUT"

# 보호자 CA 부트스트랩 — 첫 기기에서 1회
if [ ! -f "$PKI/root.key" ]; then
  openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$PKI/root.key" -out "$PKI/root.crt" -days "$CA_DAYS" \
    -subj "/CN=Babycat Local Authority" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  chmod 600 "$PKI/root.key"
  echo "보호자 CA를 새로 생성했다: $PKI/root.crt"
fi

# SAN 구성 — IPv6은 제외하고, 글자가 있으면 DNS, 아니면 IP로 분류한다
SAN=""
for h in $HOSTS; do
  case "$h" in
    *:*) continue ;;
    *[a-z]*) SAN="$SAN,DNS:$h" ;;
    *) SAN="$SAN,IP:$h" ;;
  esac
done
SAN=${SAN#,}

openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
  -keyout "$OUT/key.pem" -subj "/CN=Babycat gateway" 2>/dev/null |
openssl x509 -req -CA "$PKI/root.crt" -CAkey "$PKI/root.key" \
  -days "$DAYS" -set_serial "$(date +%s)" \
  -extfile /dev/fd/3 3<<EOF -out "$OUT/cert.pem"
subjectAltName = $SAN
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF

chmod 600 "$OUT/key.pem"
openssl x509 -in "$OUT/cert.pem" -noout -ext subjectAltName -enddate
echo "클라이언트에 설치할 CA 루트: $PKI/root.crt"

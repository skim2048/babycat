#!/bin/sh
# 게이트웨이 서빙용 인증서 발급.
#
# 운용 모델: CA는 보호자(설치 소유자) 단위로 하나이고, 펫하우스(babycat 기기)가
# 늘 때마다 이 스크립트로 그 기기의 인증서만 발급한다. 클라이언트(폰·브라우저)는
# 보호자 CA 하나만 신뢰하면 되므로 기기가 늘어도 재설정이 없다.
# - 첫 기기: CA가 없으면 스크립트가 생성한다.
# - 추가 기기: 첫 기기의 data/caddy/caddy/pki를 복사해 온 뒤 실행한다.
#
# 인증서는 모든 접속 호스트를 SAN에 담은 단일 파일이다 — IP로 접속하는
# 브라우저는 SNI를 보내지 않아 이름별 인증서 선택이 동작하지 않기 때문이다.
#
# 사용법(저장소 루트에서, HOSTS는 접속에 쓸 IP·호스트명 목록):
#   HOSTS="$(hostname -I) localhost" docker run --rm -e HOSTS \
#     -v ./data/caddy:/data/caddy \
#     -v ./docker/gateway/issue-cert.sh:/issue-cert.sh:ro babycat-router sh /issue-cert.sh
#   docker compose up -d
set -eu

HOSTS="${HOSTS:?접속 호스트 목록을 -e HOSTS로 지정해야 한다 (예: HOSTS=\"\$(hostname -I) localhost\")}"
DAYS=820     # 서빙 인증서 — macOS·iOS의 상한(825일) 이내
CA_DAYS=3650 # 보호자 CA 루트

PKI=/data/caddy/caddy/pki/authorities/local
OUT=/data/caddy/site
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
echo "클라이언트에 설치할 CA 루트: data/caddy/caddy/pki/authorities/local/root.crt"

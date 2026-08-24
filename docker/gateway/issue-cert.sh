#!/bin/sh
# 게이트웨이 서빙용 단일 multi-SAN 인증서 발급.
#
# IP 접속 브라우저는 SNI를 보내지 않아 이름별 인증서 선택이 동작하지 않으므로,
# 모든 접속 호스트를 SAN에 담은 인증서 하나를 기존 루트 CA(root.key)로 직접
# 서명해 data/caddy/site/에 둔다. 클라이언트가 신뢰하는 루트는 바뀌지 않는다.
#
# 사용법(저장소 루트에서, 접속 호스트가 바뀌면 HOSTS를 고쳐 재실행):
#   docker run --rm -v ./data/caddy:/data/caddy \
#     -v ./docker/gateway/issue-cert.sh:/issue-cert.sh:ro babycat-router sh /issue-cert.sh
#   docker compose restart gateway
set -eu

HOSTS="192.168.1.207 172.27.1.207 127.0.0.1 localhost"
DAYS=820  # macOS·iOS의 상한(825일) 이내

PKI=/data/caddy/caddy/pki/authorities/local
OUT=/data/caddy/site
mkdir -p "$OUT"

SAN=""
for h in $HOSTS; do
  case "$h" in
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

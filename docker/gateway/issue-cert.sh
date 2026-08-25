#!/bin/sh
# 게이트웨이 서빙 인증서 발급. 평시에는 게이트웨이가 기동 시 스스로 호출하므로
# (entrypoint.sh) 운영자가 직접 실행할 일이 없다.
#
# 운용 모델(docs/ops/pki.md): 서명 CA는 $PKI/root.{crt,key}에 있는 것을 쓴다.
# - 제품 기기: 출고 시 탑재한 Device CA(제조사 Root CA가 발급)가 그 자리에 있다.
#   클라이언트는 제조사 Root CA 하나만 신뢰하므로 기기가 늘어도 재설정이 없다.
# - 개발 기기: 파일이 없으면 자체 root CA를 생성하고, 그 root.crt를 클라이언트에
#   설치한다.
# 서빙 인증서 파일(cert.pem)은 리프 + 서명 CA의 체인이다 — 클라이언트는 Device CA를
# 모르고 Root CA만 알기 때문이다.
#
# 인증서는 모든 접속 호스트를 SAN에 담은 단일 파일이다 — IP로 접속하는
# 브라우저는 SNI를 보내지 않아 이름별 인증서 선택이 동작하지 않기 때문이다.
#
# 환경 변수: HOSTS(필수, 공백 구분), CADDY_DATA(caddy 데이터 루트, 기본 /data/caddy)
set -eu

HOSTS="${HOSTS:?접속 호스트 목록이 필요하다 (예: HOSTS=\"192.168.1.10 localhost\")}"
CADDY_DATA="${CADDY_DATA:-/data/caddy}"
DAYS=820     # 서빙 인증서 — macOS·iOS의 상한(825일) 이내
CA_DAYS=3650 # 개발용 자체 root CA

PKI="$CADDY_DATA/caddy/pki/authorities/local"
OUT="$CADDY_DATA/site"
mkdir -p "$PKI" "$OUT"

# 개발용 자체 root CA 부트스트랩 — Device CA가 탑재되지 않은 기기에서 1회
if [ ! -f "$PKI/root.key" ]; then
  openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$PKI/root.key" -out "$PKI/root.crt" -days "$CA_DAYS" \
    -subj "/CN=Babycat Local Authority" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  chmod 600 "$PKI/root.key"
  echo "개발용 자체 CA를 새로 생성했다: $PKI/root.crt"
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
cat "$PKI/root.crt" >> "$OUT/cert.pem"  # 체인: 리프 + 서명 CA
openssl x509 -in "$OUT/cert.pem" -noout -subject -issuer -ext subjectAltName -enddate

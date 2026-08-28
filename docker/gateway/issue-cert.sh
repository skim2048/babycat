#!/bin/sh
# Gateway server certificate issuance. Normally the gateway calls this itself at start
# (entrypoint.sh), so the operator never runs it directly.
#
# Operating model (docs/ops/pki.md): the signing CA is whatever sits at $PKI/root.{crt,key}.
# - Product device: the Device CA installed at shipment (issued by the manufacturer Root CA) is there.
#   Clients trust only the single manufacturer Root CA, so adding devices needs no reconfiguration.
# - Development device: if the files are absent, a self-made root CA is created and its root.crt
#   is installed on clients.
# The server certificate file (cert.pem) is the chain leaf + signing CA — because clients do not
# know the Device CA and only know the Root CA.
#
# The certificate is a single file carrying every connection host in the SAN — because browsers
# connecting by IP send no SNI, so per-name certificate selection does not work.
#
# Environment variables: HOSTS (required, space-separated), CADDY_DATA (caddy data root, default /data/caddy)
set -eu

HOSTS="${HOSTS:?connection host list is required (e.g. HOSTS=\"192.168.1.10 localhost\")}"
CADDY_DATA="${CADDY_DATA:-/data/caddy}"
DAYS=820     # server certificate — within the macOS/iOS limit (825 days)
CA_DAYS=3650 # self-made root CA for development

PKI="$CADDY_DATA/caddy/pki/authorities/local"
OUT="$CADDY_DATA/site"
mkdir -p "$PKI" "$OUT"

# Bootstrap of the self-made development root CA — once, on devices without an installed Device CA
if [ ! -f "$PKI/root.key" ]; then
  openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -keyout "$PKI/root.key" -out "$PKI/root.crt" -days "$CA_DAYS" \
    -subj "/CN=Babycat Local Authority" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  chmod 600 "$PKI/root.key"
  echo "Created a new self-made development CA: $PKI/root.crt"
fi

# Build the SAN — skip IPv6; classify as DNS if it contains letters, otherwise as IP
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
cat "$PKI/root.crt" >> "$OUT/cert.pem"  # chain: leaf + signing CA
openssl x509 -in "$OUT/cert.pem" -noout -subject -issuer -ext subjectAltName -enddate

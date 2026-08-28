#!/bin/sh
# Device provisioning — issues a per-device Device CA with the manufacturer Root CA.
# Run on the development PC before shipment; not used inside the gateway container.
# The procedure and key-custody rules are in docs/ops/pki.md.
#
# Usage:
#   tools/provision-device.sh init                 create the Root CA (once)
#   tools/provision-device.sh issue <serial>       issue a Device CA → provision/<serial>/
#
# Environment variables:
#   ROOT_DIR  directory holding the Root CA (default ~/.babycat-ca). Keep it outside the repository.
#   OUT_DIR   parent directory of the issued output (default ./provision, gitignored)
set -eu

ROOT_DIR="${ROOT_DIR:-$HOME/.babycat-ca}"
OUT_DIR="${OUT_DIR:-$(dirname "$0")/../provision}"
ROOT_DAYS=7300    # Root CA 20 years — kept long since renewal is distributed via mewly updates
DEVICE_DAYS=3650  # Device CA 10 years — beyond the lifetime of a pethouse device
CURVE=P-256

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

init_root() {
  if [ -f "$ROOT_DIR/root.key" ]; then
    echo "Root CA already exists: $ROOT_DIR/root.key" >&2; exit 1
  fi
  mkdir -p "$ROOT_DIR"; chmod 700 "$ROOT_DIR"
  openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:$CURVE -nodes \
    -keyout "$ROOT_DIR/root.key" -out "$ROOT_DIR/root.crt" -days "$ROOT_DAYS" \
    -subj "/O=Babycat/CN=Babycat Root CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  chmod 600 "$ROOT_DIR/root.key"
  echo "Root CA created. Back up the private key and keep it outside the repository: $ROOT_DIR"
  echo "Root certificate to bundle with mewly: $ROOT_DIR/root.crt"
}

issue_device() {
  serial="${1:?serial is required (e.g. BC-2026-00000001)}"
  case "$serial" in
    BC-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
    *) echo "serial format is BC-<year>-<8-digit sequence number>: $serial" >&2; exit 1 ;;
  esac
  [ -f "$ROOT_DIR/root.key" ] || { echo "Root CA not found. Run init first: $ROOT_DIR" >&2; exit 1; }

  # Output in the same layout as the path the gateway reads (PKI in issue-cert.sh).
  # The file names root.crt/root.key follow Caddy's pki layout; the content is the Device CA.
  dest="$OUT_DIR/$serial/caddy/pki/authorities/local"
  if [ -e "$dest/root.key" ]; then
    echo "serial already issued: $dest" >&2; exit 1
  fi
  mkdir -p "$dest"

  # nameConstraints — prevents a leaked Device CA from issuing certificates outside private addresses.
  # The server certificate's SAN (HOST_IP and TLS_EXTRA_HOSTS) must fall within this range.
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
  echo "Device CA issued: $dest/root.crt"
  echo "Copy $OUT_DIR/$serial/caddy under data/caddy/ on the device, then boot it for the first time."
}

case "${1:-}" in
  init) init_root ;;
  issue) shift; issue_device "$@" ;;
  *) usage ;;
esac

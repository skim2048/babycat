#!/bin/sh
# Bring Babycat up on this board with one command:
#
#   tools/up.sh
#
# - Creates .env interactively when it does not exist (HOST_IP and the initial
#   account; everything else keeps the .env.example defaults).
# - Creates the data directories owned by the current user (Docker would
#   otherwise create them owned by root).
# - Prints which CA will sign the server certificate (shipped Device CA, or a
#   self-made development CA on first boot).
# - Runs docker compose up -d --build and summarizes the preflight and
#   gateway results.
# Safe to re-run: every step is skipped or idempotent when already done.
set -eu

cd "$(dirname "$0")/.."

# 1. .env
if [ ! -f .env ]; then
  echo "== .env not found — creating one (see .env.example for every knob)"
  echo "addresses of this board: $(hostname -I 2>/dev/null || echo unknown)"
  printf "HOST_IP (reachable address; comma-separated list allowed): "
  read -r host_ip < /dev/tty
  [ -n "$host_ip" ] || { echo "HOST_IP is required" >&2; exit 1; }
  printf "DEFAULT_USER (initial admin account name): "
  read -r default_user < /dev/tty
  [ -n "$default_user" ] || { echo "DEFAULT_USER is required" >&2; exit 1; }
  printf "DEFAULT_PASS (initial password; a change is forced on first login): "
  read -r default_pass < /dev/tty
  [ -n "$default_pass" ] || { echo "DEFAULT_PASS is required" >&2; exit 1; }
  sed -e "s|^HOST_IP=.*|HOST_IP=$host_ip|" \
      -e "s|^DEFAULT_USER=.*|DEFAULT_USER=$default_user|" \
      -e "s|^DEFAULT_PASS=.*|DEFAULT_PASS=$default_pass|" \
      .env.example > .env
  echo ".env written"
fi

# 2. Data directories — owned by the invoking user, not root (see README)
mkdir -p data/db/router data/db/recorder data/models \
         data/state/analyzer data/state/recorder data/clips data/caddy

# 3. Which CA signs the server certificate
DEVICE_CA=data/caddy/caddy/pki/authorities/local/root.crt
if [ -f "$DEVICE_CA" ]; then
  echo "== signing CA: $(openssl x509 -in "$DEVICE_CA" -noout -subject 2>/dev/null || echo 'unreadable (root-owned; issued at first boot)')"
else
  echo "== signing CA: none installed — a development CA will be created at first boot"
  echo "   (for a product board, install the Device CA first: see docs/ops/pki.md)"
fi

# 4. Up
docker compose up -d --build

# 5. Summary
echo "== preflight"
docker compose logs preflight 2>/dev/null | sed 's/^.*| //' | grep 'preflight:' | tail -5
echo "== gateway"
docker compose logs gateway 2>/dev/null | sed 's/^.*| //' | grep -E 'issuer=|subject=' | tail -2 || true

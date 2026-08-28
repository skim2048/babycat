#!/bin/sh
# Secure a certificate before start — issue one if it is missing, the connection hosts changed, or expiry is near.
# Connection hosts are taken as-is from HOST_IP in .env (comma-separated); any further addresses
# are added via TLS_EXTRA_HOSTS. The operator never creates a certificate separately.
set -eu

# Skip issuance when invoked for an ad-hoc command (diagnostics etc.) rather than starting caddy
if [ "${1:-}" != "caddy" ]; then
  exec "$@"
fi

CADDY_DATA=/data
HOSTS=$(echo "${HOST_IP:-} ${TLS_EXTRA_HOSTS:-} localhost 127.0.0.1" |
  tr ',' ' ' | tr -s ' ' | sed 's/^ *//; s/ *$//')
export CADDY_DATA HOSTS

MARKER="$CADDY_DATA/site/hosts"
CERT="$CADDY_DATA/site/cert.pem"

need_issue=1
if [ -f "$CERT" ] && [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$HOSTS" ]; then
  # renew starting 30 days before expiry
  if openssl x509 -in "$CERT" -noout -checkend 2592000 >/dev/null 2>&1; then
    need_issue=0
  fi
fi

if [ "$need_issue" = 1 ]; then
  echo "gateway: issuing the server certificate ($HOSTS)"
  sh /usr/local/bin/issue-cert.sh
  printf '%s' "$HOSTS" > "$MARKER"
fi

exec "$@"

#!/bin/sh
# 기동 전 인증서 확보 — 없거나, 접속 호스트가 바뀌었거나, 만료가 임박하면 발급한다.
# 접속 호스트는 .env의 HOST_IP(쉼표 구분)를 그대로 쓰고, 그 밖의 주소가 필요하면
# TLS_EXTRA_HOSTS로 더한다. 운영자가 인증서를 따로 만들 일은 없다.
set -eu

# caddy 기동이 아닌 임시 명령(진단 등)으로 부를 때는 발급을 건너뛴다
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
  # 만료 30일 전부터 갱신한다
  if openssl x509 -in "$CERT" -noout -checkend 2592000 >/dev/null 2>&1; then
    need_issue=0
  fi
fi

if [ "$need_issue" = 1 ]; then
  echo "gateway: 서빙 인증서를 발급한다 ($HOSTS)"
  sh /usr/local/bin/issue-cert.sh
  printf '%s' "$HOSTS" > "$MARKER"
fi

exec "$@"

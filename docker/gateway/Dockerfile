# @claude Babycat — TLS 종단 게이트웨이. 공식 Caddy에 openssl만 더해,
# @claude 기동 시 인증서를 스스로 발급할 수 있게 한다(entrypoint.sh).

FROM caddy:2

RUN apk add --no-cache openssl

COPY docker/gateway/issue-cert.sh docker/gateway/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/issue-cert.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

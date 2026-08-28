# @claude Babycat — TLS termination gateway. Adds only openssl to the official Caddy
# @claude so it can issue its own certificate at start (entrypoint.sh).

FROM caddy:2.11.4

RUN apk add --no-cache openssl

COPY docker/gateway/issue-cert.sh docker/gateway/entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/issue-cert.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]

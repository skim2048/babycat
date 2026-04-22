---
name: babycat-api-contract-check
description: Use when changing app or api endpoints, schemas, proxy behavior, token handling, or frontend consumers so the public contract stays aligned across producers, consumers, tests, and docs.
---

# babycat-api-contract-check

## When to use

- When changing `api/*.py`, `app/server.py`, `web/src/composables/*`, or `web/vite.config.js`.
- When altering auth behavior, response shape, request body shape, proxy forwarding, or SSE fields.

## Do not use when

- The change is purely visual and does not alter any request, response, or state contract.
- The task only touches internal helper logic with no external consumer impact.

## Steps

1. Identify the endpoint or contract surface being changed.
2. Check the producer implementation.
3. Check every known consumer in `web/`, tests, and docs.
4. Confirm auth expectations, token transport, and error shape.
5. Update or flag docs/tests that no longer match.

## Definition of done

- Producer and consumer expectations match.
- Contract-sensitive docs/tests are updated or explicitly flagged as pending.

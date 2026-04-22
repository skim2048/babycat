# API Layer Rules

## Ownership

- `api/` owns authentication, refresh-token flow, SQLite persistence, event history, device tokens, and clip REST endpoints.
- `api/` is the external contract layer for clients, including proxied `app/` features that are exposed as stable API behavior.

## Change Checks

- Before changing auth, check `web/src/composables/useAuth.js`, `web/src/composables/useFetch.js`, and shared JWT assumptions with `app/`.
- Before changing schemas or responses, check producer code, web consumers, docs, and tests together.
- Before changing clip APIs, remember files are written by `app/` and resolved by filename convention plus year/month directory inference.
- Before changing DB schema, check migration and existing DB compatibility first.
- Before changing proxy behavior, check upstream error handling and web-visible failure modes.
- Before changing CORS or token query fallback, treat it as an external contract change.

## Validation

- Prefer tests that cover auth, token rotation, clip lookup, and proxy response shape.
- If a change alters external API behavior, update docs and call out any untested contract risk.

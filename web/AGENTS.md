# Web Layer Rules

## Ownership

- `web/` owns the operator dashboard and consumes both `api` and `app`.
- Do not assume the dashboard talks to a single backend.
- Do not treat `web/` as the default refactor center when the real ownership sits in `app` or `api`.

## Change Checks

- For every new request, identify whether the source of truth is `api` or `app` before editing UI code.
- Change `web/` on its own only when it has a clear local problem, or when it is misreading backend state or contract.
- Treat `/api/*` as API-server contract work.
- Treat `/events`, `/prompt`, `/ptz`, `/camera`, and `/vlm/*` as app-server contract work.
- Treat SSE, MJPEG, HLS, and WebRTC as stream flows with different auth and failure modes from normal REST.
- Before changing clip UI, check token query usage, range download behavior, metadata display, and refresh timing.
- Before changing login/session behavior, check refresh-token retry and 401/429 handling.
- Before changing `vite.config.js`, check proxy routing and deployment impact together.

## Validation

- Prefer validation that covers login, token refresh, empty state, camera apply flow, stream connection, and clip actions.
- If backend behavior cannot be exercised, call out which UI states remain assumption-based.

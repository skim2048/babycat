# Babycat Architecture Boundaries

Internal reference for developers and Codex. Use this document before refactoring or changing behavior across `app`, `api`, `web`, `config`, `tests`, and `docs`.

## Why This Exists

- Babycat is not a single app. It is a connected system with separate runtime owners.
- A small change in one layer can silently break another layer.
- Before editing code, identify the owner, source of truth, affected consumers, and verification path.

## Layer Map

### `app/`

- Responsibility: live pipeline, frame processing, VLM inference, trigger detection, clip recording, PTZ control, live SSE/MJPEG state.
- Source of truth: runtime execution state, live inference state, camera apply behavior, trigger clip creation.
- Main consumers: `web` for SSE/MJPEG/PTZ/prompt/model switch, `api` for proxied camera reads/writes, `data/` for clip files.
- Always check with: `config/`, `api/`, `web/`, `docs/api.md`.

### `api/`

- Responsibility: authentication, refresh-token flow, SQLite persistence, event/device REST, clip REST, selected `app` proxy endpoints.
- Source of truth: external client contract for auth and persisted REST behavior.
- Main consumers: `web`, future external clients, `tests/`, `docs/api.md`.
- Always check with: `app/`, `web/`, `tests/`, `docs/`.

### `web/`

- Responsibility: operator dashboard, session handling, live monitoring UI, camera settings UI, clip UI.
- Source of truth: none for business state. `web` presents and coordinates state owned by `api` and `app`.
- Main consumers: browser users.
- Always check with: `api/`, `app/`, `web/vite.config.js`.

### `config/`

- Responsibility: runtime configuration files used by containers and startup flows.
- Source of truth: persisted camera profile and MediaMTX runtime configuration.
- Main consumers: `app`, Docker services, operators.
- Always check with: `app/`, `docker-compose.yml`, `docker/`.

### `tests/`

- Responsibility: protect auth, clip-path, and selected runtime assumptions.
- Source of truth: none. Tests describe expected behavior; they do not define runtime ownership.
- Main consumers: developers and Codex.
- Always check with: the layer whose contract is being validated.

### `docs/`

- Responsibility: explain external API behavior and internal operating boundaries.
- Source of truth: none. Docs must follow code and current runtime contracts.
- Main consumers: developers, operators, Codex.
- Always check with: `app/`, `api/`, `web/`, `config/`.

## Core Flows

### Auth

- Owner: `api/`
- Flow: `web` logs in through `/api/login` and chooses either a persistent session (`remember_me=true`) or a non-persistent session (`remember_me=false`). Persistent sessions must not show a session-expiry warning modal and should stay signed in through automatic renewal. Non-persistent sessions must warn before expiry, provide at least `extend` and `logout` actions, and should not restore after the browser closes. `web` then calls both `api` and `app` with the shared JWT, and any session-renewal path must keep `api` and `web` behavior aligned.
- Watch for: token transport differences, 401/429 behavior, shared `JWT_SECRET`, query-token support for headerless clients.

### Camera Apply

- Owner: runtime apply is `app/`; external contract is split between `api` and `app`.
- Flow: `web` writes camera settings, `api` may proxy camera requests, `app` persists `config/cam_profile.json`, reconfigures PTZ, updates MediaMTX source, and resumes the live pipeline.
- Watch for: saved password behavior, startup reload, MediaMTX readiness, pipeline restart side effects.

### Clip Save / List / Delete

- Owner: clip creation is `app/`; client-facing clip REST is `api/`.
- Flow: `app` records clips into `data/{YYYY}/{MM}` and writes sidecar metadata, `api` lists/resolves/deletes files from the shared volume, `web` uses `api` for clip actions.
- Watch for: filename convention, year/month path inference, sidecar metadata compatibility, range download behavior.

### Stream / SSE

- Owner: MediaMTX owns HLS/WebRTC transport; `app` owns MJPEG and SSE payloads.
- Flow: camera RTSP is routed through MediaMTX for live playback, while `app` serves MJPEG debug frames and SSE runtime snapshots directly; `web` consumes both paths and chooses playback transport at runtime.
- Watch for: auth differences, `HOST_IP` and WebRTC wiring, SSE field changes, MJPEG query-token usage, runtime HLS/WebRTC fallback behavior.

## Cross-Boundary Changes

Treat these as multi-layer changes even if only one file is edited:

- endpoint or route changes
- request or response schema changes
- SSE payload changes
- auth or token transport changes
- proxy routing changes
- env var changes
- `config/` file format changes
- clip naming, path, or metadata changes

## Before Refactoring

Check these in order:

1. Which layer owns the behavior?
2. Which file or config is the source of truth?
3. Which other layers consume that behavior?
4. What can fail at runtime if the change is wrong?
5. What is the smallest useful verification?

## High-Risk Areas To Delay

- Large `app` pipeline decomposition before contract and validation boundaries are clearer.
- Stream fallback redesign across HLS/WebRTC/MJPEG without verifying MediaMTX and auth behavior together.
- `config/cam_profile.json` format changes without a compatibility rule.

## Safe First Refactor Areas

- clarify docs and boundary ownership
- tighten test selection and contract coverage notes
- simplify `web` request boundaries between `api` and `app`

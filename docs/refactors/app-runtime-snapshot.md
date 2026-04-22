# Refactoring Checklist: App Runtime Snapshot

## 1. Change Summary

- Refactoring target: `app` runtime snapshot and SSE payload assembly
- Main flow: `Shared Runtime State`
- Reason for change: separate snapshot assembly responsibilities without changing the public SSE contract

## 2. Responsibility Boundary

- Owner layer: `app`
- Producer: `app/state.py`
- Consumer: `web`, `docs/api.md`, any SSE client
- Adjacent layers to review: `app/server.py`, `web/src/composables/useSSE.js`

## 3. Boundary Preservation Checks

- public SSE field names must remain unchanged
- clip count and prompt/trigger fields must remain derived from the same owner state
- PTZ and hardware fields must still be included in the same client-facing snapshot

## 4. Minimum Validation

- Required checks from the validation guide: public SSE fields preserved, cache and runtime fields remain consistent
- Automated checks to run: `python -m pytest tests/test_app_state.py -q`
- Manual checks to run: static review against `web/src/composables/useSSE.js` and `docs/api.md`

## 5. Result

- What was validated:
  - snapshot assembly was split into pipeline, runtime, PTZ, and uptime helpers without changing public SSE field names
  - `python -m pytest tests/test_app_state.py -q` passed
  - static review confirms the fields consumed by `web/src/composables/useSSE.js` remain present
- What was not validated:
  - live SSE delivery through `app/server.py`
  - runtime interaction with real hardware metrics, PTZ polling, and live clip creation
- Remaining risk:
  - this refactor preserves the public snapshot contract by direct tests and static review, but end-to-end runtime behavior still depends on live Jetson, PTZ, and clip-update conditions

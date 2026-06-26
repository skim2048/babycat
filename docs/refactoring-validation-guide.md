# Babycat Refactoring Validation Guide

Use this guide after choosing a refactoring target. The goal is not to prove that "the app still runs" in the abstract. The goal is to confirm that the change stayed inside the intended responsibility boundary and did not silently change another layer's contract.

Read this together with [architecture-boundaries.md](architecture-boundaries.md).
Record each refactoring task with [refactoring-checklist-template.md](refactoring-checklist-template.md).

## How To Use This Guide

1. Identify the main flow touched by the refactor.
2. Confirm which layer owns that flow.
3. Check the listed consumers and adjacent layers.
4. Run the smallest validation that proves the boundary was preserved.
5. If a listed check cannot be run, record the remaining risk explicitly.

## Auth

- Owner: `api`
- Check with: `web`, `app` JWT verification assumptions, `docs/api.md`, `tests/test_api.py`
- Use when: login, refresh-token flow, logout, password change, token parsing, auth error handling
- Minimum validation:
  - `/api/login` response shape still matches `web` expectations
  - refresh-token rotation still works as expected
  - `401` and `429` behavior remains consistent for clients
  - JWT issued by `api` is still accepted by `app`

## Camera Apply

- Owner: runtime apply is `app`; client-facing contract is shared between `api` and `app`
- Check with: `web`, `config/cam_profile.json`, MediaMTX config/update path, PTZ setup
- Use when: camera settings UI, camera proxy routes, saved password logic, startup reload, apply flow
- Minimum validation:
  - camera profile can still be read and applied through the current client path
  - saved credentials behavior is unchanged unless intentionally modified
  - MediaMTX source update still happens on apply
  - configured state and apply failure state are still visible to the client

## Clip Flow

- Owner: clip creation is `app`; client-facing clip contract is `api`
- Check with: `web`, `data/{YYYY}/{MM}`, sidecar metadata, clip lookup/delete code, `tests/test_api.py`
- Use when: clip naming, clip storage path, metadata shape, listing, download, delete, cache behavior
- Minimum validation:
  - new and existing clip names still resolve correctly
  - list output still includes expected metadata fields
  - download behavior still matches existing route and range expectations
  - delete behavior still removes the matching metadata sidecar when expected

## Stream And SSE

- Owner: MediaMTX owns HLS/WebRTC transport; `app` owns MJPEG and SSE payloads
- Check with: `web`, MediaMTX runtime wiring, `docs/api.md`
- Use when: HLS, WebRTC, MJPEG, SSE, live status payloads, stream auth handling
- Minimum validation:
  - `web` still connects to the same stream path it expects
  - MJPEG and SSE auth path is unchanged unless intentionally modified
  - SSE payload fields used by `web` are still present
  - WebRTC/HLS wiring assumptions are unchanged or explicitly documented

## Web Request Routing

- Owner: `web` for request selection; `api` and `app` remain the behavior owners
- Check with: `web/vite.config.js`, `web/src/composables/*`, `api`, `app`
- Use when: composable cleanup, fetch wrapper changes, route/proxy changes, UI-side request consolidation
- Minimum validation:
  - each request still targets the correct owner layer
  - auth-bearing requests still send tokens in the expected way
  - proxy changes do not silently move a contract from `api` to `app`, or the reverse
  - error handling still matches the upstream source

## Shared Runtime State

- Owner: `app`
- Check with: `web`, `docs/api.md`, any code consuming SSE snapshots or clip counts
- Use when: shared state shape, SSE snapshot assembly, runtime cache behavior, app-side view model cleanup
- Minimum validation:
  - public SSE fields consumed by `web` are preserved
  - cached state still invalidates at the same boundary conditions unless intentionally changed
  - clip count and camera-related state remain consistent with runtime behavior

## Config And Environment

- Owner: mixed; treat as cross-boundary by default
- Check with: `docker-compose.yml`, `docker/`, `config/`, `app`, `api`, README
- Use when: env vars, startup defaults, config file format, mounted paths, runtime source-of-truth changes
- Minimum validation:
  - the owning service for each value is still clear
  - startup assumptions still match compose and container config
  - config format changes are documented and compatibility risk is called out

## What Counts As Success

A refactor is validated when:

- the changed flow still belongs to the same owner layer unless ownership was intentionally redesigned
- consumer-facing contracts remain stable, or the contract change is explicit and coordinated
- the smallest checks needed for that flow were run or the remaining risk was stated clearly

## What This Guide Does Not Do

- It does not replace unit tests or runtime checks.
- It does not claim full hardware validation on a non-Jetson machine.
- It does not justify skipping cross-layer review when the change crosses a published contract.

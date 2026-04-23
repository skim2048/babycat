# Refactoring Checklist: Web Request Routing

## 1. Change Summary

- Refactoring target: `web` request routing and endpoint ownership visibility
- Main flow: `Web Request Routing`
- Reason for change: make `api`, `app`, and MediaMTX ownership explicit without changing client behavior

## 2. Responsibility Boundary

- Owner layer: `web` chooses request targets; runtime behavior remains owned by `api`, `app`, or MediaMTX
- Producer: route constants and request selection in `web`
- Consumer: `web` composables and components
- Adjacent layers to review: `api`, `app`, `web/vite.config.js`, MediaMTX port assumptions

## 3. Boundary Preservation Checks

- Existing request paths must remain unchanged
- Auth routes must remain `api` owned
- PTZ, prompt, SSE, and VLM switch routes must remain `app` owned
- camera profile routes must target the `api` proxy contract consumed by the frontend
- HLS and WHEP playback URLs must remain MediaMTX owned

## 4. Minimum Validation

- Required checks from the validation guide: correct owner layer, token transport preserved, upstream error handling preserved
- Automated checks to run: `npm run build`
- Manual checks to run: static review of every updated request call site

## 5. Result

- What was validated:
  - all updated `web` request call sites now reference a shared owner map in `web/src/endpoints.js`
  - auth routes remain mapped to `api`
  - camera routes are mapped to `api`, which continues to proxy the upstream `app` camera contract
  - PTZ, prompt, SSE, and VLM switch routes remain mapped to `app`
  - clip routes remain mapped to `api`
  - HLS and WHEP playback URLs remain mapped to MediaMTX ports `8888` and `8889`
  - `node --check` passed for the new endpoint module and the updated plain JavaScript composables
- What was not validated:
  - `npm run build` could not run because `web/node_modules/.bin/vite` is not present in the current workspace
  - browser runtime behavior was not exercised
- Remaining risk:
  - this refactor preserves route strings by static review, but frontend runtime regressions remain unverified until dependencies are available and the dashboard is exercised

# Refactoring Checklist: Camera Apply Error Surface

## 1. Change Summary

- Refactoring target: `web/src/composables/useCamera.js` error handling
- Main flow: `Camera Apply`
- Reason for change: keep the camera apply contract unchanged while making load and save failures surface the existing server-side message more consistently

## 2. Responsibility Boundary

- Owner layer: `web`
- Producer: `useCamera.js`
- Consumer: `CameraPanel.vue`, dashboard operators
- Adjacent layers to review: `api` camera proxy error format, `app` camera apply error format

## 3. Boundary Preservation Checks

- `app` and `api` response shapes remain unchanged
- `web` continues to accept both `ok:false` and HTTP error responses
- auth redirect behavior still belongs to `authFetch`

## 4. Minimum Validation

- Required checks from the validation guide: apply failure state remains visible to the client, current client path still uses the same owner layers
- Automated checks to run: `node --check web/src/composables/useCamera.js`
- Manual checks to run: static review that `error` and `detail` are both surfaced to the user

## 5. Result

- What was validated:
  - load and save paths now parse camera responses defensively
  - `ok:false`, FastAPI `detail`, and generic HTTP failures now converge on one status path in `useCamera.js`
  - `node --check web/src/composables/useCamera.js` passed
- What was not validated:
  - browser-visible error text during live camera failures
- Remaining risk:
  - the UI now surfaces server messages more consistently, but the practical quality of those messages still depends on `app` and `api` error wording

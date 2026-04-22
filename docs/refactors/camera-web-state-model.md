# Refactoring Checklist: Camera Web State Model

## 1. Change Summary

- Refactoring target: `web/src/composables/useCamera.js` derived camera state
- Main flow: `Camera Apply`
- Reason for change: move camera-related derived state into the camera composable so views stop reinterpreting raw config fields independently

## 2. Responsibility Boundary

- Owner layer: `web`
- Producer: `useCamera.js`
- Consumer: `LiveStream.vue`, `DashboardView.vue`, camera UI
- Adjacent layers to review: stored camera profile contract, PTZ visibility, preferred stream protocol handling

## 3. Boundary Preservation Checks

- persisted camera config fields remain unchanged
- PTZ visibility still depends on the same ONVIF capability
- the saved stream preference remains the single source for preferred transport

## 4. Minimum Validation

- Required checks from the validation guide: request ownership unchanged, camera-related UI state still derives from the same owner fields
- Automated checks to run: `node --check web/src/composables/useCamera.js`
- Manual checks to run: static review of `LiveStream.vue` and `DashboardView.vue`

## 5. Result

- What was validated:
  - `useCamera.js` now exports derived camera state for preferred transport, PTZ enablement, and screen state
  - `LiveStream.vue` and `DashboardView.vue` consume those derived values instead of reinterpreting raw config locally
  - `node --check web/src/composables/useCamera.js` passed
- What was not validated:
  - browser-visible state transitions on a live dashboard
- Remaining risk:
  - the ownership is clearer, but runtime UI timing still depends on browser playback and live camera conditions

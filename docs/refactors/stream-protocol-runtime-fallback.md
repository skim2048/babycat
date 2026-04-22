# Refactoring Checklist: Stream Protocol Runtime Fallback

## 1. Change Summary

- Refactoring target: `web/src/components/LiveStream.vue` runtime stream selection
- Main flow: `Stream And SSE`
- Reason for change: separate stored stream preference from the actual transport used during a live connection so fallback behavior matches the documented contract

## 2. Responsibility Boundary

- Owner layer: `web` for runtime transport selection
- Producer: `LiveStream.vue` and `useCamera.js`
- Consumer: dashboard operators and MediaMTX-backed playback paths
- Adjacent layers to review: `docs/api.md`, MediaMTX HLS/WHEP endpoints, stored `stream_protocol` contract

## 3. Boundary Preservation Checks

- stored `stream_protocol` remains the persisted client preference
- HLS and WHEP endpoints remain unchanged
- runtime fallback must not rewrite the saved preference silently

## 4. Minimum Validation

- Required checks from the validation guide: stream paths unchanged, transport assumptions explicit, client-facing contract preserved
- Automated checks to run: `node --check web/src/composables/useCamera.js`
- Manual checks to run: static review that fallback changes only the active runtime transport

## 5. Result

- What was validated:
  - stored `stream_protocol` is normalized and kept as the preferred transport
  - `LiveStream.vue` now tracks the active transport separately and falls back once per connection attempt
  - MediaMTX endpoint selection remains HLS `:8888` and WHEP `:8889`
  - `node --check web/src/composables/useCamera.js` passed
- What was not validated:
  - browser playback against live MediaMTX
  - real WebRTC/HLS failure and fallback timing
- Remaining risk:
  - runtime fallback logic is structurally clearer, but actual fallback behavior still depends on browser, MediaMTX, and network conditions

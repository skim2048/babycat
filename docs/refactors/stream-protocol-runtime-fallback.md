# Refactoring Checklist: Stream Protocol Runtime Fallback

## 1. Change Summary

- Refactoring target: `web/src/components/LiveStream.vue` runtime stream selection
- Main flow: `Stream And SSE`
- Reason for change: remove stored client protocol preference and let live transport selection stay in web runtime state so fallback behavior matches the documented contract

## 2. Responsibility Boundary

- Owner layer: `web` for runtime transport selection
- Producer: `LiveStream.vue`
- Consumer: dashboard operators and MediaMTX-backed playback paths
- Adjacent layers to review: `docs/api.md`, MediaMTX HLS/WHEP endpoints, camera profile contract, and config compatibility

## 3. Boundary Preservation Checks

- camera profile no longer persists a client-selected playback transport
- HLS and WHEP endpoints remain unchanged
- runtime fallback remains transient and must not leak into saved camera configuration

## 4. Minimum Validation

- Required checks from the validation guide: stream paths unchanged, transport assumptions explicit, client-facing contract preserved
- Automated checks to run: `node --check web/src/composables/useCamera.js`
- Manual checks to run: static review that fallback changes only runtime transport state and starts from WebRTC first

## 5. Result

- What was validated:
  - `LiveStream.vue` now owns the active transport state and falls back once per connection attempt
  - MediaMTX endpoint selection remains HLS `:8888` and WHEP `:8889`
  - `node --check web/src/composables/useCamera.js` passed
- What was not validated:
  - browser playback against live MediaMTX
  - real WebRTC/HLS failure and fallback timing
- Remaining risk:
  - runtime fallback logic is structurally clearer, but actual fallback behavior still depends on browser, MediaMTX, and network conditions

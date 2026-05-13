# Refactoring Checklist: Stream Protocol Selection

## 1. Change Summary

- Refactoring target: `web/src/components/LiveStream.vue` runtime stream selection
- Main flow: `Stream And SSE`
- Reason for change: replace automatic runtime fallback with an operator-selected HLS/WebRTC preference stored in browser localStorage

## 2. Responsibility Boundary

- Owner layer: `web` for runtime transport selection
- Producer: `LiveStream.vue`
- Consumer: dashboard operators and MediaMTX-backed playback paths
- Adjacent layers to review: `docs/api.md`, MediaMTX HLS/WHEP endpoints, camera profile contract, and config compatibility

## 3. Boundary Preservation Checks

- camera profile does not persist a client-selected playback transport
- HLS and WHEP endpoints remain unchanged
- protocol preference remains browser-local and must not leak into saved camera configuration

## 4. Minimum Validation

- Required checks from the validation guide: stream paths unchanged, transport assumptions explicit, client-facing contract preserved
- Automated checks to run: `npx vite build --configLoader runner`
- Manual checks to run: static review that selection changes only browser playback state and starts from HLS when localStorage has no saved value

## 5. Result

- What was validated:
  - `LiveStream.vue` now owns the preferred transport state and stores it in browser localStorage
  - MediaMTX endpoint selection remains HLS `:8888` and WHEP `:8889`
  - `npx vite build --configLoader runner` passed
- What was not validated:
  - browser playback against live MediaMTX
  - real WebRTC/HLS switching against a live camera
- Remaining risk:
  - WebRTC connectivity still depends on browser, MediaMTX, `HOST_IP`, UDP `8890`, and network conditions

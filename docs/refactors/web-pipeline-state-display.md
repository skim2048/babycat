Flow: Stream And SSE
Owner: web for display; app remains the owner of pipeline state
Producer: `app` SSE snapshot
Consumer: `web/src/components/LiveStream.vue`, `web/src/composables/useSSE.js`
Checks: Web must display app-owned pipeline state and detail without reinterpreting them as browser playback state; new fields stay additive to existing SSE consumption.
Validated: `useSSE.js` now exposes derived pipeline display helpers, `LiveStream.vue` consumes those helpers instead of redefining the same mapping locally, and `node --check` passed for both files.
Remaining risk: Browser rendering and live SSE updates were not exercised in this environment.

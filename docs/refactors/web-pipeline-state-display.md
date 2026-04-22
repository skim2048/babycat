Flow: Stream And SSE
Owner: web for display; app remains the owner of pipeline state
Producer: `app` SSE snapshot
Consumer: `web/src/components/LiveStream.vue`, `web/src/composables/useSSE.js`
Checks: Web must display app-owned pipeline state without reinterpreting it as browser playback state; new fields stay additive to existing SSE consumption.
Validated: `node --check web/src/composables/useSSE.js`, extracted `<script setup>` from `LiveStream.vue` checked with `node --check`.
Remaining risk: Browser rendering and live SSE updates were not exercised in this environment.

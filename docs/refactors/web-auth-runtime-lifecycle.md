Flow: Auth / Stream And SSE / Clip Flow
Owner: `web` for session-scoped consumer lifecycle; `api` and `app` contracts remain unchanged
Producer: `web/src/composables/useAuth.js`, `web/src/composables/useSSE.js`, `web/src/composables/useClips.js`
Consumer: dashboard session state, SSE connection lifecycle, clip panel refresh behavior
Checks: token changes must reconnect headerless SSE consumers, logout must clear client-held clip state, request ownership must remain unchanged
Validated: `useAuth.js` exposes readonly token state for other composables, `useSSE.js` now reconnects on token change and clears state on logout, `useClips.js` now resets clip state when authentication ends and only reacts to clip-count updates while authenticated
Remaining risk: browser login/logout and token-refresh behavior were not exercised against live services in this environment

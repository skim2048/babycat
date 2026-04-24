Flow: Auth / Stream And SSE / Clip Flow
Owner: `web` for session-scoped consumer lifecycle; session policy must stay aligned with `api` auth contracts
Producer: `web/src/composables/useAuth.js`, `web/src/composables/useSSE.js`, `web/src/composables/useClips.js`
Consumer: dashboard session state, SSE connection lifecycle, clip panel refresh behavior
Checks: persistent sessions must not show a session-expiry warning modal; non-persistent sessions must warn before expiry and expose at least `extend` and `logout`; token changes must reconnect headerless SSE consumers; logout must clear client-held clip state; request ownership must remain unchanged
Validated: policy baseline only. Code still needs to be refactored so storage choice, warning-modal behavior, session extension, logout cleanup, and token refresh behavior match the updated policy
Remaining risk: current runtime behavior still reflects the older token-storage and refresh contract until implementation and tests are updated

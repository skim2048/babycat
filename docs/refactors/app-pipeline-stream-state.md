Flow: Stream And SSE
Owner: app
Producer: GStreamer pipeline lifecycle in `app/main.py` and shared snapshot assembly in `app/state.py`
Consumer: `web` SSE client, `docs/api.md`
Checks: App-owned pipeline state must stay separate from browser playback state; SSE remains additive; restart causes remain visible as app-side reasons.
Validated: `tests/test_app_state.py`, AST parse for `app/main.py` and `app/server.py`, docs updated for new SSE fields.
Remaining risk: Jetson + MediaMTX runtime behavior was not exercised here, so real frame stalls and restart timing still need live verification.

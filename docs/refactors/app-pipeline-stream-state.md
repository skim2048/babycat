Flow: Stream And SSE
Owner: app
Producer: GStreamer pipeline lifecycle in `app/main.py` and shared snapshot assembly in `app/state.py`
Consumer: `web` SSE client, `docs/api.md`
Checks: App-owned pipeline state must stay separate from browser playback state; SSE remains additive; pipeline state detail values remain visible as app-owned context; `waiting_for_vlm` must not remain after `vlm_state=ready`.
Validated: `tests/test_app_state.py`, AST parse for `app/main.py` and `app/server.py`, docs updated for new SSE fields.
Remaining risk: Jetson + MediaMTX runtime behavior was not exercised here, so real frame stalls and restart timing still need live verification.

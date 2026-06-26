# App Layer Rules

## Ownership

- `app/` owns the live pipeline, shared runtime state, VLM inference lifecycle, PTZ control, trigger clip recording, and MediaMTX source updates.
- Do not move auth, event history, or device registration responsibilities into `app/`.

## Change Checks

- Before changing the pipeline entry or inference flow, check timing, worker/thread interaction, clip save flow, and model lifecycle impact.
- Before changing shared runtime state or SSE fields, check impact on `web/` and `docs/api.md`.
- Before changing camera/profile flow, check config persistence, PTZ reconfiguration, MediaMTX API update, and pipeline restart behavior.
- Before changing clip naming or storage rules, check `api/` clip listing, lookup, and deletion compatibility.
- Before changing PTZ behavior, check saved home position format and UI expectations.

## Validation

- Treat performance-sensitive refactors as behavior changes until proven otherwise.
- Prefer verification that covers frame flow, SSE state, camera apply flow, and clip handling.
- If hardware-specific validation is unavailable, call out the exact Jetson/NVIDIA risk left open.

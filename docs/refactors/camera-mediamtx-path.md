# Refactoring Checklist: Camera Apply Shared Activation Paths

## 1. Change Summary

- Refactoring target: shared PTZ, MediaMTX, and ready-state activation paths inside `app/camera.py`
- Main flow: `Camera Apply`
- Reason for change: remove the smallest internal duplication between manual apply and startup apply without changing camera behavior

## 2. Responsibility Boundary

- Owner layer: `app`
- Producer: `app/camera.py`
- Consumer: `app/server.py`, startup pipeline boot, MediaMTX runtime configuration
- Adjacent layers to review: `config/cam_profile.json`, PTZ setup, `api` camera proxy, `web` camera save flow

## 3. Boundary Preservation Checks

- camera profile persistence remains in `app/camera.py`
- PTZ configuration still happens before MediaMTX source update
- apply success and failure results remain unchanged for callers

## 4. Minimum Validation

- Required checks from the validation guide: current client path still applies the camera profile and MediaMTX source update remains part of that flow
- Automated checks to run: `python -m pytest tests/test_app_camera.py -q`
- Manual checks to run: static review that `apply()` and `startup_apply()` now share the same MediaMTX apply helper

## 5. Result

- What was validated:
  - `apply()` and `startup_apply()` now use the same helper structure for runtime activation order
  - `apply()` and `startup_apply()` still preserve PTZ-before-MediaMTX behavior
  - `python -m pytest tests/test_app_camera.py -q` passed
- What was not validated:
  - live MediaMTX API interaction
  - browser-visible camera save behavior
- Remaining risk:
  - this refactor changes only the shared internal path, but real MediaMTX availability and full camera apply behavior still depend on runtime environment

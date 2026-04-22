# Refactoring Checklist: Camera Shared Activation, Profile, And Input Rules

## 1. Change Summary

- Refactoring target: shared PTZ, MediaMTX, ready-state activation, camera-profile response paths, and input normalization rules inside `app/camera.py`
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
- current supported input source remains `rtsp_camera`, while ONVIF becomes optional runtime capability

## 4. Minimum Validation

- Required checks from the validation guide: current client path still applies the camera profile and MediaMTX source update remains part of that flow
- Automated checks to run: `python -m pytest tests/test_app_camera.py -q`
- Manual checks to run: static review that `apply()` and `startup_apply()` now share the same MediaMTX apply helper

## 5. Result

- What was validated:
  - `apply()` and `startup_apply()` now use the same helper structure for runtime activation order
  - `apply()` and `startup_apply()` still preserve PTZ-before-MediaMTX behavior
  - camera profile response shaping now comes from `app/camera.py` instead of being duplicated in `app/server.py`
  - input normalization now treats `rtsp_camera` as the current source type and allows ONVIF to be omitted
  - `stream_protocol` now has an explicit UI-facing contract: `hls` or `webrtc`, with fallback to `hls`
  - `python -m pytest tests/test_app_camera.py -q` passed
- What was not validated:
  - live MediaMTX API interaction
  - browser-visible camera save behavior
- Remaining risk:
  - this refactor changes only the shared internal path, but real MediaMTX availability and full camera apply behavior still depend on runtime environment

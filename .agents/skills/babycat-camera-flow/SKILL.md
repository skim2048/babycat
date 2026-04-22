---
name: babycat-camera-flow
description: Use when changing or debugging camera profile, PTZ, or MediaMTX source behavior so config persistence, runtime apply flow, and UI-visible state stay consistent.
---

# babycat-camera-flow

## When to use

- When touching `app/camera.py`, PTZ flow, camera settings UI, or camera-related API/proxy behavior.
- When debugging camera apply failures, saved credential behavior, or startup reload issues.

## Do not use when

- The work is unrelated to camera configuration or PTZ behavior.
- The task only concerns clip listing or auth without camera flow impact.

## Steps

1. Check how the camera profile is read and persisted.
2. Check how saved credentials are handled.
3. Check how PTZ is reconfigured from the saved profile.
4. Check how MediaMTX source update is triggered and what happens on failure.
5. Check how web reflects configured, connecting, and error states.

## Definition of done

- Persistence, runtime apply, PTZ setup, MediaMTX update, and UI state have all been considered.
- Camera work is not treated as a UI-only or config-only change.

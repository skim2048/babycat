---
name: babycat-streaming-debug
description: Use when investigating RTSP, MediaMTX, HLS, WebRTC, MJPEG, or SSE problems to locate whether the break is in source input, streaming middleware, app runtime, or web consumption.
---

# babycat-streaming-debug

## When to use

- When live video does not appear.
- When MJPEG or SSE is empty or unstable.
- When HLS or WebRTC connects inconsistently.
- When the symptom may come from camera, MediaMTX, app, or web.

## Do not use when

- The issue is clearly unrelated to streaming or live state delivery.
- The task is only about static API responses or database behavior.

## Steps

1. Identify which stream path is failing: RTSP, HLS, WebRTC, MJPEG, or SSE.
2. Check the upstream dependency chain for that path.
3. Confirm auth expectations for that path.
4. Check whether the failure is source input, MediaMTX wiring, app state production, or web consumption.
5. State the narrowest confirmed failing boundary before proposing fixes.

## Definition of done

- The failing stream path and boundary are identified.
- The investigation does not stop at the first visible symptom in the UI.

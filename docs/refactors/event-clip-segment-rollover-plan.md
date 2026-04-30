Flow: Event Clip Segment Rollover
Owner: app
Producer: trigger-clip capture path in `app/main.py`
Consumers: `api` clip REST, `web` clip UI, `data/` storage policy
Problem:
- Current trigger clips start a fresh `ffmpeg` RTSP session after VLM detection.
- Detection time and recording start time are structurally different.
- `-c:v copy` can expose keyframe/GOP alignment artifacts at clip start.
- Result: some clips can begin with visually frozen or stale-looking content, and event timing can drift before/after the user-visible action.

Immediate action:
- Keep the current architecture for now.
- Add observability for `event_time`, recorder start delay, ffmpeg elapsed time, output size/duration, and stderr summary.
- Persist these diagnostics in sidecar metadata so field issues can be reviewed after clip deletion from the UI.

Target direction:
- Move from trigger-time RTSP re-recording to short rolling segments.
- Keep recent segments in a dedicated temporary area, separate from final event clips.
- On event, finalize `pre-event + post-event` windows into one user-visible clip.

Proposed defaults:
- Segment duration: 1 second
- Rolling window: 10 to 15 seconds
- Final event clip: 2 to 3 seconds before the event + 5 seconds after the event
- API/Web expose finalized event clips only

Boundary notes:
- `app` owns segment production, rollover cleanup, and final clip assembly.
- `api` remains a finalized-clip consumer and should not index temporary segments.
- `web` should keep its existing clip model unless final metadata shape changes materially.
- `data/` layout likely needs a temporary sub-tree in addition to `/data/{YYYY}/{MM}` final outputs.

Validation goals:
- Compare `event_time_ms` vs `ffmpeg_started_at_ms` on current clips.
- Confirm whether frozen-start clips correlate with large start delay or short keyframe intervals.
- Use those observations to decide whether to prototype segment rollover directly or first try a narrower recorder change.

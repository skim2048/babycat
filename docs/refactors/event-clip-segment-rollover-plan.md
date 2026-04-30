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
- Observability for `event_time`, recorder/finalizer start delay, ffmpeg elapsed time, output size/duration, and stderr summary was added.
- Sidecar metadata now carries these diagnostics for postmortem review.

Current prototype direction:
- Trigger-time RTSP re-recording was replaced with short rolling segments.
- Recent segments are kept in `/data/.segments/live` as `.ts` files, separate from final event clips.
- On event, the app finalizes a `pre-event + post-event` window into one user-visible mp4.

Proposed defaults:
- Segment duration: 1 second
- Rolling window: 10 to 15 seconds
- Final event clip: 2 seconds before the event + 5 seconds after the event
- API/Web expose finalized event clips only

Boundary notes:
- `app` owns segment production, rollover cleanup, and final clip assembly.
- `api` remains a finalized-clip consumer and should not index temporary segments.
- `web` should keep its existing clip model unless final metadata shape changes materially.
- `data/` layout likely needs a temporary sub-tree in addition to `/data/{YYYY}/{MM}` final outputs.

Validation goals:
- Compare `event_time_ms` vs finalizer timing fields on current clips.
- Confirm whether frozen-start clips disappear or shrink under the continuous-segment path.
- If artifacts remain, evaluate whether segment capture itself must re-encode to force denser keyframes.

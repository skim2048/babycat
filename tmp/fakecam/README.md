# fakecam

A throwaway RTSP source for testing [babycat](../README.md). Streams
local mp4 files over RTSP so the VLM pipeline can be exercised against
a reproducible input instead of a live camera.

## Layout

| Path | Role |
|---|---|
| `server/` | Python + GStreamer + gst-rtsp-server + FastAPI. Owns the RTSP factory, the playback state machine, and the control API on `:8090`. |
| `web/` | Vue 3 + Vite control panel on `:5174`. Browse `videos/`, build a stream queue, start/stop playback, tweak RTSP settings. |
| `videos/` | Drop mp4 files here. Picked up live by an inotify watcher. |
| `server/state/` | Persisted settings (`state.json`). Edit through the web UI; the API rejects direct file edits as inconsistent. |

## Run

```sh
docker compose up -d --build
```

- Web UI:  `http://<host>:5174`
- RTSP:    `rtsp://<user>:<password>@<host>:<port><path>` — defaults to `rtsp://admin:admin@<host>:554/live`, all four fields editable in the settings modal.
- Backend API (rarely needed directly): `http://<host>:8090`

Compose uses host networking on the backend so the RTSP port binds
directly on the host. The frontend exposes only `:5174`.

Code lives in the image, not as a bind mount — rebuild after server
changes:

```sh
docker compose up -d --build backend
```

## Use

1. Drop mp4 files under `fakecam/videos/`. They appear in the file tree
   immediately (inotify).
2. Check the files you want and click **+** to add them to the stream
   queue.
3. Press **▶**. The queue plays in order; toggle shuffle / repeat as
   needed.
4. Point a client (VLC, babycat, ffmpeg) at the RTSP URL shown in the
   dashboard.

Settings (resolution / fps / bitrate / audio / RTSP transport fields)
must be changed while playback is **stopped** — the backend returns 409
otherwise. Transport changes restart the RTSP server; encoding changes
release the active media so the next client connection rebuilds the
pipeline with the new caps.

## Known limits

- **No interactive prev/next.** The pipeline drives entirely off natural
  EOS — the queue plays through and stops (or wraps under repeat). This
  is intentional; the VLM-test workflow does not benefit from
  per-track navigation.
- **Audio is always stripped** under the current concat backend,
  regardless of the audio setting. The toggle is wired through the API
  but the launch string ignores it until a real need surfaces.
- **`media-unprepare` on stop / EOS tears down every connected client.**
  Clients that auto-retry (babycat's `rtspsrc`, VLC's reconnect) will
  loop on the refused RTSP factory until something is queued again.
  That is the intended TEARDOWN-style shutdown, not a bug.
- **Single-video H.264 input only.** Files are demuxed with `qtdemux`
  and decoded with `avdec_h264`. Other codecs/containers will fail to
  prepare.

## Developer notes

- GLib main loop runs in a daemon thread; uvicorn owns the main thread.
  Cross-thread RTSP mutations go through `GLib.idle_add`.
- Concat does not bubble EOS downstream when its last sink finishes;
  `rtsp_server.py` attaches downstream-event probes to every concat
  sink and triggers the exhausted callback directly when the last
  enqueued sink EOSs.
- `library_watcher.py` translates inotify events to SSE library updates
  so the web tree stays current without polling.

See [`PLAN.md`](PLAN.md) for the original design sketch (kept for
historical context; the current implementation has diverged in spots).

"""
Phase 0 verification: GStreamer appsink -> Python numpy array.
Run manually inside the app container; importing this module should not
start the pipeline during pytest collection.

@chatgpt
"""

import time


def main():
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    import numpy as np

    Gst.init(None)

    frame_count = 0
    start_time = None
    frame_info = {}

    def on_new_sample(sink):
        nonlocal frame_count, start_time, frame_info

        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR

        buf = sample.get_buffer()
        caps = sample.get_caps()

        if start_time is None:
            start_time = time.time()
            s = caps.get_structure(0)
            frame_info['width'] = s.get_value('width')
            frame_info['height'] = s.get_value('height')
            frame_info['format'] = s.get_value('format')
            frame_info['expected_bytes'] = frame_info['width'] * frame_info['height'] * 4
            print(f"[caps] {frame_info['width']}x{frame_info['height']} {frame_info['format']}")
            print(
                f"[caps] expected bytes/frame: {frame_info['expected_bytes']:,} "
                f"({frame_info['expected_bytes']/1024/1024:.2f} MB)"
            )

        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            print("ERROR: buffer.map() failed — NVMM buffer is not CPU-readable")
            return Gst.FlowReturn.ERROR

        frame_count += 1
        buf_size = len(map_info.data)

        if frame_count <= 3 or frame_count % 30 == 0:
            w = frame_info['width']
            h = frame_info['height']
            size_match = buf_size == frame_info['expected_bytes']

            arr = np.frombuffer(map_info.data, dtype=np.uint8)
            if size_match:
                arr = arr.reshape(h, w, 4)
                mean_rgb = arr[:, :, :3].mean()
                mean_rgb_text = f"{mean_rgb:.1f}"
                shape_text = str(arr.shape)
            else:
                mean_rgb_text = "N/A"
                shape_text = "N/A"

            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0

            print(
                f"[frame {frame_count:4d}] buf={buf_size:,}B  match={size_match}  "
                f"shape={shape_text}  mean_rgb={mean_rgb_text}  fps={fps:.1f}"
            )

        buf.unmap(map_info)
        return Gst.FlowReturn.OK

    mediamtx_url = "rtsp://127.0.0.1:8554/live"
    test_duration = 10
    pipeline_str = (
        f"rtspsrc location={mediamtx_url} latency=0 protocols=tcp "
        "! rtph264depay ! h264parse ! nvv4l2decoder "
        "! nvvidconv ! video/x-raw,format=RGBA "
        "! appsink name=sink emit-signals=true sync=false drop=true max-buffers=1"
    )

    print(f"Pipeline: {pipeline_str}\n")
    pipeline = Gst.parse_launch(pipeline_str)
    sink = pipeline.get_by_name('sink')
    sink.connect('new-sample', on_new_sample)

    pipeline.set_state(Gst.State.PLAYING)
    print(f"Pipeline PLAYING — collecting frames for {test_duration}s...\n")

    try:
        time.sleep(test_duration)
    finally:
        pipeline.set_state(Gst.State.NULL)
        elapsed = time.time() - (start_time or time.time())
        print("\n=== Result ===")
        print(f"Frames received: {frame_count}")
        print(f"Elapsed:         {elapsed:.1f}s")
        print(f"Average FPS:     {frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
        print(f"Frame size:      {frame_info.get('expected_bytes', 0)/1024/1024:.2f} MB/frame")


if __name__ == '__main__':
    main()

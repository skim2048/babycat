"""
Phase 0 검증: GStreamer appsink → Python numpy array 연동 테스트
- MediaMTX에서 RTSP 수신
- nvv4l2decoder GPU 디코딩
- nvvidconv → RGBA 변환
- appsink로 프레임을 numpy array로 수신
- 버퍼 크기, shape, FPS 출력
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import numpy as np
import time
import sys

Gst.init(None)

frame_count = 0
start_time = None
frame_info = {}

def on_new_sample(sink):
    global frame_count, start_time, frame_info

    sample = sink.emit('pull-sample')
    if sample is None:
        return Gst.FlowReturn.ERROR

    buf = sample.get_buffer()
    caps = sample.get_caps()

    if start_time is None:
        start_time = time.time()
        s = caps.get_structure(0)
        frame_info['width']  = s.get_value('width')
        frame_info['height'] = s.get_value('height')
        frame_info['format'] = s.get_value('format')
        frame_info['expected_bytes'] = frame_info['width'] * frame_info['height'] * 4  # RGBA
        print(f"[caps] {frame_info['width']}x{frame_info['height']} {frame_info['format']}")
        print(f"[caps] expected bytes/frame: {frame_info['expected_bytes']:,} "
              f"({frame_info['expected_bytes']/1024/1024:.2f} MB)")

    success, map_info = buf.map(Gst.MapFlags.READ)
    if not success:
        print("ERROR: buffer.map() failed — NVMM 버퍼를 CPU에서 읽을 수 없음")
        return Gst.FlowReturn.ERROR

    frame_count += 1
    buf_size = len(map_info.data)

    # 처음 3프레임과 이후 매 30프레임마다 상세 출력
    if frame_count <= 3 or frame_count % 30 == 0:
        w = frame_info['width']
        h = frame_info['height']
        size_match = (buf_size == frame_info['expected_bytes'])

        arr = np.frombuffer(map_info.data, dtype=np.uint8)
        if size_match:
            arr = arr.reshape(h, w, 4)
            mean_rgb = arr[:, :, :3].mean()
        else:
            mean_rgb = None

        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0

        print(f"[frame {frame_count:4d}] "
              f"buf={buf_size:,}B  match={size_match}  "
              f"shape={arr.shape if size_match else 'N/A'}  "
              f"mean_rgb={mean_rgb:.1f if mean_rgb is not None else 'N/A'}  "
              f"fps={fps:.1f}")

    buf.unmap(map_info)
    return Gst.FlowReturn.OK


MEDIAMTX_URL = "rtsp://127.0.0.1:8554/live"
TEST_DURATION = 10  # seconds

pipeline_str = (
    f'rtspsrc location={MEDIAMTX_URL} latency=0 protocols=tcp '
    '! rtph264depay ! h264parse ! nvv4l2decoder '
    '! nvvidconv ! video/x-raw,format=RGBA '
    '! appsink name=sink emit-signals=true sync=false drop=true max-buffers=1'
)

print(f"Pipeline: {pipeline_str}\n")
pipeline = Gst.parse_launch(pipeline_str)
sink = pipeline.get_by_name('sink')
sink.connect('new-sample', on_new_sample)

pipeline.set_state(Gst.State.PLAYING)
print(f"Pipeline PLAYING — {TEST_DURATION}초간 프레임 수집...\n")

try:
    time.sleep(TEST_DURATION)
finally:
    pipeline.set_state(Gst.State.NULL)
    elapsed = time.time() - (start_time or time.time())
    print(f"\n=== 결과 ===")
    print(f"수신 프레임: {frame_count}")
    print(f"경과 시간:   {elapsed:.1f}s")
    print(f"평균 FPS:    {frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
    print(f"프레임 크기: {frame_info.get('expected_bytes', 0)/1024/1024:.2f} MB/frame")

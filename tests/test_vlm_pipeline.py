"""
Babycat — VLM Phase 1 verification test.
Integrates the GStreamer pipeline with VLM inference end to end.

Validation:
  (1) Runs without errors.
  (2) Throughput matches expectations.

Run inside the app container:
  python /app/test_vlm_pipeline.py

Environment variables:
  MEDIAMTX_URL   RTSP source URL         (default: rtsp://babycat-mediamtx:8554/live)
  VLM_MODEL      NanoLLM model id        (default: Efficient-Large-Model/VILA1.5-3b)
  N_INFERENCES   number of inferences    (default: 5)
  TARGET_FPS     videorate target FPS    (default: 1.0)

@claude
"""

import gc
import os
import queue
import time
from fractions import Fraction

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

import numpy as np
from PIL import Image
from nano_llm import NanoLLM, ChatHistory

# ── Configuration ────────────────────────────────────────────────────────────

MEDIAMTX_URL  = os.getenv("MEDIAMTX_URL",  "rtsp://babycat-mediamtx:8554/live")
MODEL_ID      = os.getenv("VLM_MODEL",     "Efficient-Large-Model/VILA1.5-3b")
N_INFERENCES  = int(os.getenv("N_INFERENCES", "5"))
TARGET_FPS    = float(os.getenv("TARGET_FPS",  "1.0"))
VLM_INPUT_SIZE = (384, 384)

INFERENCE_PROMPT = "What is the person doing? Answer in one sentence."


# ── VLM inference ────────────────────────────────────────────────────────────

def run_inference(model: NanoLLM, frame: Image.Image) -> str:
    """Run single-frame VLM inference; returns the raw text. @claude"""
    chat = ChatHistory(model)
    chat.append('user', image=frame)
    chat.append('user', text=INFERENCE_PROMPT)

    embedding, _ = chat.embed_chat()
    tokens = []
    for token in model.generate(embedding, max_new_tokens=32, streaming=True):
        tokens.append(token)

    result = "".join(tokens)
    chat.reset()
    gc.collect()
    return result


# ── GStreamer callback ───────────────────────────────────────────────────────

def make_frame_callback(frame_q: queue.Queue):
    first_frame = [True]

    def on_new_sample(sink) -> Gst.FlowReturn:
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR

        buf = sample.get_buffer()
        caps = sample.get_caps()
        s = caps.get_structure(0)
        w = s.get_value('width')
        h = s.get_value('height')

        if first_frame[0]:
            fmt = s.get_value('format')
            nbytes = w * h * 4
            print(f"[pipeline] first frame: {w}x{h} {fmt}  ({nbytes/1024/1024:.2f} MB/frame)",
                  flush=True)
            first_frame[0] = False

        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            print("[pipeline] ERROR: buffer.map() failed", flush=True)
            return Gst.FlowReturn.ERROR

        arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(h, w, 4)
        img = Image.fromarray(arr[:, :, :3], mode='RGB').resize(VLM_INPUT_SIZE)
        buf.unmap(map_info)

        try:
            frame_q.put_nowait(img)
        except queue.Full:
            pass  # @claude Previous frame still unconsumed — drop.

        return Gst.FlowReturn.OK

    return on_new_sample


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 55)
    print("  Babycat VLM Phase 1 verification test")
    print("=" * 55)
    print(f"  URL          : {MEDIAMTX_URL}")
    print(f"  MODEL        : {MODEL_ID}")
    print(f"  N_INFERENCES : {N_INFERENCES}")
    print(f"  TARGET_FPS   : {TARGET_FPS}")
    print()

    # @claude 1. Load the VLM.
    print("[1/3] Loading VLM model...", flush=True)
    t0 = time.time()
    model = NanoLLM.from_pretrained(MODEL_ID, api="mlc", quantization="q4f16_ft")
    load_time = time.time() - t0
    print(f"[1/3] done ({load_time:.1f}s)\n", flush=True)

    # @claude 2. Start the pipeline.
    Gst.init(None)
    fps = Fraction(TARGET_FPS).limit_denominator(1000)
    pipeline_str = (
        f'rtspsrc location={MEDIAMTX_URL} latency=0 protocols=tcp '
        '! rtph264depay ! h264parse ! nvv4l2decoder '
        '! nvvidconv ! video/x-raw,format=RGBA '
        f'! videorate ! video/x-raw,framerate={fps.numerator}/{fps.denominator} '
        '! appsink name=sink emit-signals=true sync=false drop=true max-buffers=1'
    )

    print(f"[2/3] Starting pipeline (TARGET_FPS={TARGET_FPS})", flush=True)
    pipeline = Gst.parse_launch(pipeline_str)
    sink = pipeline.get_by_name('sink')
    frame_q: queue.Queue = queue.Queue(maxsize=1)
    sink.connect('new-sample', make_frame_callback(frame_q))
    pipeline.set_state(Gst.State.PLAYING)
    print(f"[2/3] PLAYING\n", flush=True)

    # @claude 3. Run N inferences.
    print(f"[3/3] Running inference ({N_INFERENCES} iterations)\n", flush=True)

    latencies = []
    errors = 0

    for i in range(1, N_INFERENCES + 1):
        try:
            frame = frame_q.get(timeout=10)
        except queue.Empty:
            print(f"  [{i}/{N_INFERENCES}] ERROR: frame timeout (10s)", flush=True)
            errors += 1
            continue

        t0 = time.time()
        try:
            raw = run_inference(model, frame)
            elapsed_ms = (time.time() - t0) * 1000
            latencies.append(elapsed_ms)
            print(f"  [{i}/{N_INFERENCES}] {elapsed_ms:6.0f}ms  raw='{raw.strip()}'", flush=True)
        except Exception as e:
            elapsed_ms = (time.time() - t0) * 1000
            print(f"  [{i}/{N_INFERENCES}] ERROR ({elapsed_ms:.0f}ms): {e}", flush=True)
            errors += 1

    pipeline.set_state(Gst.State.NULL)

    # @claude Summary.
    print()
    print("=" * 55)
    print("  Result summary")
    print("=" * 55)
    print(f"  Model load        : {load_time:.1f}s")
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"  Successful runs   : {len(latencies)} / {N_INFERENCES}")
        print(f"  Average latency   : {avg:.0f}ms  ({1000/avg:.2f} inferences/s)")
        print(f"  Min / max         : {min(latencies):.0f}ms / {max(latencies):.0f}ms")
    print(f"  Errors            : {errors}")
    print(f"  (1) No errors     : {'PASS' if errors == 0 else 'FAIL'}")
    if latencies:
        # @claude Per bench_vlm.py, expect ~1000ms average per single-frame inference.
        avg = sum(latencies) / len(latencies)
        within = abs(avg - 1000) < 500  # @claude 500ms..1500ms acceptable band.
        print(f"  (2) Speed check   : {'PASS' if within else 'CHECK'} "
              f"(avg {avg:.0f}ms, band 500..1500ms)")
    print()


if __name__ == '__main__':
    main()

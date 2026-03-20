"""
Wally-backend — VLM Phase 1 검증 테스트
GStreamer 파이프라인 + VLM 추론 통합 확인

검증 항목:
  (1) 오류 없이 구동되는가
  (2) 처리속도가 예상과 유사한가

실행 (app 컨테이너 내부):
  python /app/test_vlm_pipeline.py

환경변수:
  MEDIAMTX_URL   RTSP 소스 URL          (기본: rtsp://mediamtx:8554/live)
  VLM_MODEL      NanoLLM 모델 ID        (기본: Efficient-Large-Model/VILA1.5-3b)
  N_INFERENCES   추론 횟수              (기본: 5)
  TARGET_FPS     videorate 타겟 FPS     (기본: 1.0)
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

# ── 설정 ──────────────────────────────────────────────────────────────────────

MEDIAMTX_URL  = os.getenv("MEDIAMTX_URL",  "rtsp://mediamtx:8554/live")
MODEL_ID      = os.getenv("VLM_MODEL",     "Efficient-Large-Model/VILA1.5-3b")
N_INFERENCES  = int(os.getenv("N_INFERENCES", "5"))
TARGET_FPS    = float(os.getenv("TARGET_FPS",  "1.0"))
VLM_INPUT_SIZE = (384, 384)

# main.py와 동일한 프롬프트
INFERENCE_PROMPT = """\
You are a veterinary monitoring AI watching a dog inside a pet house.
Analyze the image and determine if the dog shows any of these abnormal behaviors:
- seizure: convulsions, uncontrolled muscle movements, falling over
- vomiting: active vomiting
- retching: repeated dry heaving or pre-vomit abdominal contractions
- scratching: repeated, intense scratching of body parts
- circling: spinning in tight circles repeatedly
- excessive_licking: compulsively licking body parts or surfaces
- excessive_panting: heavy panting without apparent physical exertion

If an abnormal behavior is detected, respond ONLY with:
  DETECTED: <behavior_key>
If the dog appears normal, respond ONLY with:
  NORMAL"""


# ── VLM 추론 ──────────────────────────────────────────────────────────────────

def run_inference(model: NanoLLM, frame: Image.Image) -> str:
    """단일 프레임으로 VLM 추론. raw 텍스트 반환."""
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


# ── GStreamer 콜백 ─────────────────────────────────────────────────────────────

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
            print(f"[pipeline] 첫 프레임 수신: {w}x{h} {fmt}  ({nbytes/1024/1024:.2f} MB/frame)",
                  flush=True)
            first_frame[0] = False

        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            print("[pipeline] ERROR: buffer.map() 실패", flush=True)
            return Gst.FlowReturn.ERROR

        arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(h, w, 4)
        img = Image.fromarray(arr[:, :, :3], mode='RGB').resize(VLM_INPUT_SIZE)
        buf.unmap(map_info)

        try:
            frame_q.put_nowait(img)
        except queue.Full:
            pass  # 이전 프레임 아직 미소비 — drop

        return Gst.FlowReturn.OK

    return on_new_sample


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 55)
    print("  Wally-backend VLM Phase 1 검증 테스트")
    print("=" * 55)
    print(f"  URL          : {MEDIAMTX_URL}")
    print(f"  MODEL        : {MODEL_ID}")
    print(f"  N_INFERENCES : {N_INFERENCES}")
    print(f"  TARGET_FPS   : {TARGET_FPS}")
    print()

    # 1. 모델 로드
    print("[1/3] VLM 모델 로드 중...", flush=True)
    t0 = time.time()
    model = NanoLLM.from_pretrained(MODEL_ID, api="mlc", quantization="q4f16_ft")
    load_time = time.time() - t0
    print(f"[1/3] 완료 ({load_time:.1f}s)\n", flush=True)

    # 2. 파이프라인 시작
    Gst.init(None)
    fps = Fraction(TARGET_FPS).limit_denominator(1000)
    pipeline_str = (
        f'rtspsrc location={MEDIAMTX_URL} latency=0 protocols=tcp '
        '! rtph264depay ! h264parse ! nvv4l2decoder '
        '! nvvidconv ! video/x-raw,format=RGBA '
        f'! videorate ! video/x-raw,framerate={fps.numerator}/{fps.denominator} '
        '! appsink name=sink emit-signals=true sync=false drop=true max-buffers=1'
    )

    print(f"[2/3] 파이프라인 시작 (TARGET_FPS={TARGET_FPS})", flush=True)
    pipeline = Gst.parse_launch(pipeline_str)
    sink = pipeline.get_by_name('sink')
    frame_q: queue.Queue = queue.Queue(maxsize=1)
    sink.connect('new-sample', make_frame_callback(frame_q))
    pipeline.set_state(Gst.State.PLAYING)
    print(f"[2/3] PLAYING\n", flush=True)

    # 3. N회 추론
    print(f"[3/3] 추론 시작 (총 {N_INFERENCES}회)\n", flush=True)

    latencies = []
    errors = 0

    for i in range(1, N_INFERENCES + 1):
        try:
            frame = frame_q.get(timeout=10)
        except queue.Empty:
            print(f"  [{i}/{N_INFERENCES}] ERROR: 프레임 타임아웃 (10s)", flush=True)
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

    # 요약
    print()
    print("=" * 55)
    print("  결과 요약")
    print("=" * 55)
    print(f"  모델 로드       : {load_time:.1f}s")
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"  성공 추론       : {len(latencies)} / {N_INFERENCES}")
        print(f"  평균 처리속도   : {avg:.0f}ms  ({1000/avg:.2f} inferences/s)")
        print(f"  최소 / 최대     : {min(latencies):.0f}ms / {max(latencies):.0f}ms")
    print(f"  오류 횟수       : {errors}")
    print(f"  (1) 오류 없음   : {'PASS' if errors == 0 else 'FAIL'}")
    if latencies:
        # bench_vlm.py 기준 1프레임 평균 약 1000ms 예상
        avg = sum(latencies) / len(latencies)
        within = abs(avg - 1000) < 500  # 500ms~1500ms 범위
        print(f"  (2) 속도 기준   : {'PASS' if within else 'CHECK'} "
              f"(평균 {avg:.0f}ms, 기준 500~1500ms)")
    print()


if __name__ == '__main__':
    main()

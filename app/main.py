"""
Babycat — App 메인 엔트리포인트

파이프라인:
  rtspsrc (MediaMTX) → rtph264depay → h264parse → nvv4l2decoder
  → nvvidconv (RGBA) → videorate → appsink
  → RingBuffer → VLM 추론 → 키워드 매칭 → 트리거 클립 저장
"""

import gc
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import numpy as np
from PIL import Image
from nano_llm import NanoLLM, ChatHistory

import camera
from state import state as debug_state
from server import start_server
from ptz import is_moving as ptz_is_moving

log = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────────────────────

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://babycat-mediamtx:8554/live")
MODEL_ID     = os.getenv("VLM_MODEL",    "Efficient-Large-Model/VILA1.5-3b")

TARGET_FPS = float(os.getenv("TARGET_FPS", "1.0"))
N_FRAMES   = int(os.getenv("N_FRAMES",   "4"))

RING_SIZE = int(os.getenv("RING_SIZE", "30"))

TRIGGER_COOLDOWN  = float(os.getenv("TRIGGER_COOLDOWN", "30"))
TRIGGER_CLIP_DUR  = int(os.getenv("TRIGGER_CLIP_DUR", "5"))

# SigLIP 입력 해상도 (VLM 내부에서 384×384로 리사이즈됨)
VLM_INPUT_SIZE = (384, 384)

INFERENCE_PROMPT_DEFAULT = "What is the person doing? Answer in one sentence."


# ── Ring Buffer ───────────────────────────────────────────────────────────────

class RingBuffer:
    """
    VLM 컨텍스트용 고정 크기 순환 버퍼.
    GStreamer 콜백(다른 스레드)에서 push, 추론 스레드에서 latest() 호출.
    """

    def __init__(self, maxlen: int):
        self._buf: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: Image.Image) -> None:
        with self._lock:
            self._buf.append(frame)

    def latest(self, n: int) -> list:
        """가장 최근 n개 프레임을 반환. n보다 적으면 있는 것만 반환."""
        with self._lock:
            frames = list(self._buf)
        return frames[-n:] if len(frames) >= n else frames

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


# ── 트리거 클립 저장 ─────────────────────────────────────────────────────────

_trigger_last_save: float = 0.0
_trigger_lock = threading.Lock()


def save_trigger_clip(matched_keywords: list[str], event_time: float) -> None:
    """
    트리거 키워드 이벤트 발생 시 ffmpeg로 RTSP 스트림에서 TRIGGER_CLIP_DUR초 직접 녹화.
    TRIGGER_COOLDOWN 이내 재호출은 무시.
    """
    global _trigger_last_save
    with _trigger_lock:
        if event_time - _trigger_last_save < TRIGGER_COOLDOWN:
            return
        _trigger_last_save = event_time

    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(event_time))
    tag = "_".join(matched_keywords[:3])
    clip_dir = debug_state.get_clip_dir()
    if not clip_dir:
        log.warning("No clip directory set — skipping trigger clip")
        return
    dest_dir = Path(clip_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{ts}_{tag}.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-rtsp_transport", "tcp",
        "-i", MEDIAMTX_URL,
        "-t", str(TRIGGER_CLIP_DUR),
        "-c:v", "copy", "-c:a", "aac",
        str(out_path),
    ]
    log.info("trigger-clip recording start: %s (%ds)", out_path.name, TRIGGER_CLIP_DUR)
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=TRIGGER_CLIP_DUR + 10)
        log.info("trigger-clip recording done: %s", out_path.name)
    except subprocess.TimeoutExpired:
        log.warning("trigger-clip recording timeout: %s", out_path.name)
    except Exception as e:
        log.error("trigger-clip recording error: %s", e)


# ── VLM 추론 ──────────────────────────────────────────────────────────────────

def run_inference(model: NanoLLM, frames: list) -> str:
    """
    PIL 프레임 리스트로 VLM 추론 실행.
    ChatHistory API 사용 (NanoLLM 멀티모달 올바른 방법).
    chat.reset() + gc.collect() 필수 (NanoLLM GitHub issue #39, 메모리 누수 방지).
    """
    chat = ChatHistory(model)
    for img in frames:
        chat.append('user', image=img)
    chat.append('user', text=debug_state.get_prompt())

    embedding, _ = chat.embed_chat()
    tokens = []
    for token in model.generate(embedding, max_new_tokens=32, streaming=True):
        tokens.append(token)

    raw = "".join(tokens).replace("</s>", "").strip()
    chat.reset()
    gc.collect()

    return raw


# ── 추론 워커 스레드 ───────────────────────────────────────────────────────────

def inference_worker(model: NanoLLM, ring: RingBuffer,
                     infer_queue: queue.Queue) -> None:
    """
    appsink 콜백이 infer_queue에 신호를 보내면 ring에서 최신 N_FRAMES를 꺼내
    VLM 추론 → 키워드 매칭 → 필요 시 트리거 클립 저장.
    """
    log.info("VLM inference thread started")
    while True:
        try:
            infer_queue.get(timeout=5)
        except queue.Empty:
            continue

        if ptz_is_moving():
            continue

        frames = ring.latest(N_FRAMES)
        if not frames:
            continue

        t0 = time.time()
        try:
            raw = run_inference(model, frames)
        except Exception as e:
            log.error("VLM inference error: %s", e)
            continue
        elapsed_ms = (time.time() - t0) * 1000

        # 트리거 키워드 매칭
        triggers = debug_state.get_triggers()
        raw_lower = raw.lower()
        matched = [kw for kw in triggers if kw in raw_lower] if triggers else []
        event_triggered = len(matched) > 0

        if event_triggered:
            log.info("%.0fms -> EVENT: %s", elapsed_ms, matched)
        else:
            log.info("%.0fms -> normal", elapsed_ms)

        debug_state.update_inference(
            "EVENT" if event_triggered else "정상",
            raw, elapsed_ms,
            event_triggered=event_triggered)

        if event_triggered:
            threading.Thread(
                target=save_trigger_clip, args=(matched, time.time()), daemon=True
            ).start()


# ── GStreamer 파이프라인 ───────────────────────────────────────────────────────

def build_pipeline_str(url: str, target_fps: float) -> str:
    """
    파이프라인 문자열 생성.
    videorate로 FPS 정규화: 카메라 원본 FPS에 무관하게 균일 간격 프레임 추출.
    """
    fps = Fraction(target_fps).limit_denominator(1000)
    return (
        f'rtspsrc location={url} latency=0 protocols=tcp '
        '! rtph264depay ! h264parse ! nvv4l2decoder '
        '! nvvidconv ! video/x-raw,format=RGBA '
        f'! videorate ! video/x-raw,framerate={fps.numerator}/{fps.denominator} '
        '! appsink name=sink emit-signals=true sync=false drop=true max-buffers=1'
    )


def make_frame_callback(ring: RingBuffer, infer_queue: queue.Queue):
    """
    appsink 'new-sample' 시그널 콜백 생성.
    - RGBA 버퍼 → numpy → PIL (384×384 RGB) → RingBuffer push
    - 추론 큐에 신호 전송 (큐가 가득 찬 경우 drop — 이전 추론 진행 중)
    """
    def on_new_sample(sink) -> Gst.FlowReturn:
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR

        buf = sample.get_buffer()
        caps = sample.get_caps()
        s = caps.get_structure(0)
        w = s.get_value('width')
        h = s.get_value('height')

        success, map_info = buf.map(Gst.MapFlags.READ)
        if not success:
            log.error("buffer.map() failed")
            return Gst.FlowReturn.ERROR

        try:
            arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(h, w, 4)
            img = Image.fromarray(arr[:, :, :3], mode='RGB').resize(VLM_INPUT_SIZE)
        except Exception as e:
            log.error("frame conversion failed: %s", e)
            return Gst.FlowReturn.OK
        finally:
            buf.unmap(map_info)

        ring.push(img)
        debug_state.update_frame(img, w, h)

        try:
            infer_queue.put_nowait(True)
        except queue.Full:
            pass

        return Gst.FlowReturn.OK

    return on_new_sample


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    log.info("=== Babycat App start ===")
    log.info("  MEDIAMTX_URL : %s", MEDIAMTX_URL)
    log.info("  MODEL_ID     : %s", MODEL_ID)
    log.info("  TARGET_FPS   : %s", TARGET_FPS)
    log.info("  N_FRAMES     : %s", N_FRAMES)
    log.info("  RING_SIZE    : %s", RING_SIZE)

    # VLM 모델 로드
    log.info("Loading VLM model: %s", MODEL_ID)
    t0 = time.time()
    model = NanoLLM.from_pretrained(MODEL_ID, api="mlc", quantization="q4f16_ft")
    log.info("Model loaded (%.1fs)", time.time() - t0)

    # 컴포넌트 초기화
    ring    = RingBuffer(maxlen=RING_SIZE)
    infer_q = queue.Queue(maxsize=1)

    # 초기 프롬프트 및 베이스 디렉토리 설정
    debug_state.set_prompt(INFERENCE_PROMPT_DEFAULT)
    debug_state.set_cam_base_dir(camera.CAM_BASE_DIR)

    # 디버그 대시보드에 참조 전달
    debug_state.set_refs(ring, RING_SIZE, {
        "target_fps": TARGET_FPS,
        "n_frames":   N_FRAMES,
    })

    # 디버그 웹서버 시작 (파이프라인보다 먼저 — RTSP 미연결 시에도 대시보드 접근 가능)
    start_server(8080)

    # 저장된 카메라 설정 적용 (MediaMTX 재시도 포함)
    threading.Thread(target=camera.startup_apply, daemon=True).start()
    log.info("Waiting for camera config (max 60s)...")
    if camera.camera_ready.wait(timeout=60):
        log.info("Camera config applied")
        # 카메라 설정에서 클립 디렉토리 결정
        config = camera.load()
        if config and config.get("name"):
            debug_state.set_clip_dir(camera.get_clip_dir(config))
        else:
            # name 없는 레거시 설정 — 임시 디렉토리 사용
            legacy_dir = os.path.join(camera.CAM_BASE_DIR, "_legacy")
            debug_state.set_clip_dir(legacy_dir)
            log.warning("Camera config has no name — clips will be saved to %s", legacy_dir)
    else:
        log.info("Camera not configured — set via frontend")

    # 레거시 클립 디렉토리 경고
    for legacy in [Path("/app/clip"), Path("/app/cam")]:
        if legacy.exists() and any(legacy.rglob("*.mp4")):
            log.warning(
                "Legacy clips found in %s. "
                "Move them to %s/_legacy/ to access via API.",
                legacy, camera.CAM_BASE_DIR,
            )

    # 추론 워커 스레드 시작
    worker = threading.Thread(
        target=inference_worker,
        args=(model, ring, infer_q),
        daemon=True,
    )
    worker.start()

    # GStreamer 파이프라인 초기화
    Gst.init(None)
    pipeline_str = build_pipeline_str(MEDIAMTX_URL, TARGET_FPS)
    log.info("Pipeline: %s", pipeline_str)

    pipeline = Gst.parse_launch(pipeline_str)
    sink = pipeline.get_by_name('sink')
    sink.connect('new-sample', make_frame_callback(ring, infer_q))

    pipeline.set_state(Gst.State.PLAYING)
    log.info("Pipeline PLAYING")

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        log.info("Shutdown signal received")
    finally:
        pipeline.set_state(Gst.State.NULL)
        log.info("Pipeline stopped")


if __name__ == '__main__':
    main()

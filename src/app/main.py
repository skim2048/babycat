"""
Wally-backend — App 메인 엔트리포인트
Phase 1: GStreamer 파이프라인 + VLM 추론 + 이벤트 판정

파이프라인 (Branch B):
  rtspsrc (MediaMTX) → rtph264depay → h264parse → nvv4l2decoder
  → nvvidconv (RGBA) → videorate → appsink
  → RingBuffer → VLM 추론 → EventJudge → FCM 알림
"""

import gc
import json
import os
import queue
import shutil
import threading
import time
from collections import deque
from fractions import Fraction
from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import numpy as np
import requests as http_requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from PIL import Image
from nano_llm import NanoLLM, ChatHistory

from debug_server import state as debug_state, start_debug_server

# ── 설정 ──────────────────────────────────────────────────────────────────────

MEDIAMTX_URL = os.getenv("MEDIAMTX_URL", "rtsp://mediamtx:8554/live")
MODEL_ID     = os.getenv("VLM_MODEL",    "Efficient-Large-Model/VILA1.5-3b")

# Branch B 프레임 샘플링 (OI-02: Phase 1에서 실 데이터 기반 결정)
TARGET_FPS = float(os.getenv("TARGET_FPS", "1.0"))  # videorate 타겟 (fps)
N_FRAMES   = int(os.getenv("N_FRAMES",   "4"))       # 추론당 프레임 수

# Ring Buffer 크기 (OI-04: 1fps × 30s = 30프레임, ~237MB RGBA)
RING_SIZE = int(os.getenv("RING_SIZE", "30"))

# 연속 감지 조건 (OI-03: 오탐 방지. N회 연속 동일 감지 시 알림)
CONSEC_N = int(os.getenv("CONSEC_N", "3"))

# FCM 알림 설정 (비어있으면 FCM 비활성화 — 로그 출력만)
FCM_CREDENTIALS = os.getenv("FCM_CREDENTIALS", "")   # service account JSON 파일 경로
FCM_TOKEN       = os.getenv("FCM_TOKEN",       "")   # 수신 기기 FCM 등록 토큰

# 클립 저장 설정 (MediaMTX 세그먼트 → events 디렉토리로 복사)
RECORDINGS_DIR    = os.getenv("RECORDINGS_DIR",    "/recordings/live")    # MediaMTX 세그먼트 경로
EVENTS_DIR        = os.getenv("EVENTS_DIR",        "/recordings/events")  # 이벤트 클립 보존 경로
CLIP_PRE_SEGMENTS = int(os.getenv("CLIP_PRE_SEGMENTS", "2"))              # 보존할 세그먼트 수 (60s × 2 = 최대 2분)

# SigLIP 입력 해상도 (VLM 내부에서 384×384로 리사이즈됨, 추론 시간에 무관)
VLM_INPUT_SIZE = (384, 384)

# ── 감지 대상 행동 ─────────────────────────────────────────────────────────────

BEHAVIORS = {
    "seizure":            "경련 (발작)",
    "vomiting":           "구토",
    "retching":           "헛구역질",
    "scratching":         "긁기 과다",
    "circling":           "선회운동",
    "excessive_licking":  "핥기 과다",
    "excessive_panting":  "헐떡임 과다",
}

# INFERENCE_PROMPT = """\
# You are a veterinary monitoring AI watching a dog inside a pet house.
# Analyze the image and determine if the dog shows any of these abnormal behaviors:
# - seizure: convulsions, uncontrolled muscle movements, falling over
# - vomiting: active vomiting
# - retching: repeated dry heaving or pre-vomit abdominal contractions
# - scratching: repeated, intense scratching of body parts
# - circling: spinning in tight circles repeatedly
# - excessive_licking: compulsively licking body parts or surfaces
# - excessive_panting: heavy panting without apparent physical exertion
#
# If an abnormal behavior is detected, respond ONLY with:
#   DETECTED: <behavior_key>
# If the dog appears normal, respond ONLY with:
#   NORMAL"""

INFERENCE_PROMPT = "What is the person doing? Answer in one sentence."


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


# ── 이벤트 판정 ───────────────────────────────────────────────────────────────

class EventJudge:
    """
    같은 행동이 CONSEC_N회 연속 감지될 때 알림을 발령.
    다른 결과(NORMAL 포함)가 나오면 streak 초기화.
    알림 발령 직후에도 streak를 초기화하여 반복 발령 방지.
    """

    def __init__(self, consec_n: int = CONSEC_N):
        self._consec_n = consec_n
        self._streak: dict = {}

    def update(self, detected: Optional[str]) -> Optional[str]:
        """
        detected: 행동 키(e.g. 'scratching') 또는 None(정상)
        반환: 알림 발령할 행동 키, 없으면 None
        """
        if detected is None:
            self._streak.clear()
            return None

        count = self._streak.get(detected, 0) + 1
        self._streak = {detected: count}  # 다른 행동의 streak 초기화

        if count >= self._consec_n:
            self._streak[detected] = 0  # 발령 후 즉시 초기화
            return detected

        return None


# ── FCM 알림 ──────────────────────────────────────────────────────────────────

_fcm_creds: Optional[service_account.Credentials] = None
_fcm_project_id: Optional[str] = None


def init_fcm() -> bool:
    """
    FCM service account credentials 초기화.
    FCM_CREDENTIALS 파일이 없으면 False 반환 (FCM 비활성화).
    """
    global _fcm_creds, _fcm_project_id
    if not FCM_CREDENTIALS:
        return False
    try:
        with open(FCM_CREDENTIALS) as f:
            info = json.load(f)
        _fcm_project_id = info.get("project_id")
        _fcm_creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
        return True
    except Exception as e:
        print(f"[FCM] credentials 로드 실패: {e}", flush=True)
        return False


def preserve_clip(behavior: str, event_time: float) -> None:
    """
    MediaMTX 세그먼트 디렉토리에서 최근 CLIP_PRE_SEGMENTS개를 이벤트 디렉토리로 복사.
    recordDeleteAfter(2h)로 삭제되기 전에 보존.
    현재 쓰기 중인 세그먼트도 포함될 수 있으나 fmp4 포맷은 부분 파일도 재생 가능.
    """
    src_dir = Path(RECORDINGS_DIR)
    if not src_dir.exists():
        print(f"[clip] 녹화 디렉토리 없음: {src_dir}", flush=True)
        return

    segments = sorted(src_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not segments:
        print("[clip] 보존할 세그먼트 없음", flush=True)
        return

    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(event_time))
    dest_dir = Path(EVENTS_DIR) / f"{ts}_{behavior}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for seg in segments[:CLIP_PRE_SEGMENTS]:
        shutil.copy2(seg, dest_dir / seg.name)
        print(f"[clip] 보존: {seg.name} → {dest_dir}", flush=True)

    print(f"[clip] 클립 저장 완료: {dest_dir}", flush=True)


def send_alert(behavior: str) -> None:
    """
    FCM HTTP v1 API로 푸시 알림 발송 + 이벤트 클립 보존.
    FCM_CREDENTIALS 또는 FCM_TOKEN 미설정 시 로그 출력만.
    """
    label = BEHAVIORS.get(behavior, behavior)
    print(f"[ALERT] 이상 행동 감지: {label} ({behavior})", flush=True)

    # 클립 보존 (별도 스레드 — 파일 복사 동안 추론 스레드 블로킹 방지)
    threading.Thread(
        target=preserve_clip, args=(behavior, time.time()), daemon=True
    ).start()

    if not _fcm_creds or not FCM_TOKEN:
        return

    if not _fcm_creds.valid:
        _fcm_creds.refresh(GoogleAuthRequest())

    url = (
        f"https://fcm.googleapis.com/v1/projects/{_fcm_project_id}/messages:send"
    )
    payload = {
        "message": {
            "token": FCM_TOKEN,
            "notification": {
                "title": "Wally-backend 이상 행동 감지",
                "body": f"반려견이 {label}을(를) 보이고 있습니다.",
            },
            "data": {"behavior": behavior},
        }
    }
    try:
        resp = http_requests.post(
            url,
            headers={
                "Authorization": f"Bearer {_fcm_creds.token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        if resp.ok:
            print("[FCM] 알림 발송 성공", flush=True)
        else:
            print(f"[FCM] 알림 발송 실패: {resp.status_code} {resp.text}", flush=True)
    except Exception as e:
        print(f"[FCM] 알림 발송 오류: {e}", flush=True)


# ── VLM 추론 ──────────────────────────────────────────────────────────────────

def parse_vlm_response(text: str) -> Optional[str]:
    """
    VLM 출력 파싱.
    'DETECTED: <key>' → 행동 키 반환
    'NORMAL' 또는 파싱 실패 → None 반환
    """
    text = text.strip()
    if text.upper().startswith("DETECTED:"):
        key = text.split(":", 1)[1].strip().lower()
        # </s> 등 EOS 토큰 제거
        key = key.split("<")[0].strip()
        if key in BEHAVIORS:
            return key
        # "none of the above" 등 정상 응답을 DETECTED: 형식으로 출력한 경우 무시
        if "none" not in key:
            print(f"[WARN] 알 수 없는 행동 키: {key!r}", flush=True)
    return None


def run_inference(model: NanoLLM, frames: list) -> tuple[Optional[str], str]:
    """
    PIL 프레임 리스트로 VLM 추론 실행.
    ChatHistory API 사용 (NanoLLM 멀티모달 올바른 방법).
    chat.reset() + gc.collect() 필수 (NanoLLM GitHub issue #39, 메모리 누수 방지).

    반환: (행동 키 또는 None, VLM 원본 텍스트)
    """
    chat = ChatHistory(model)
    for img in frames:
        chat.append('user', image=img)
    chat.append('user', text=INFERENCE_PROMPT)

    embedding, _ = chat.embed_chat()
    tokens = []
    for token in model.generate(embedding, max_new_tokens=32, streaming=True):
        tokens.append(token)

    raw = "".join(tokens).replace("</s>", "").strip()
    chat.reset()
    gc.collect()

    return parse_vlm_response(raw), raw


# ── 추론 워커 스레드 ───────────────────────────────────────────────────────────

def inference_worker(model: NanoLLM, ring: RingBuffer, judge: EventJudge,
                     infer_queue: queue.Queue) -> None:
    """
    appsink 콜백이 infer_queue에 신호를 보내면 ring에서 최신 N_FRAMES를 꺼내
    VLM 추론 → 이벤트 판정 → 필요 시 알림 발송.
    """
    print("[worker] VLM 추론 스레드 시작", flush=True)
    while True:
        try:
            infer_queue.get(timeout=5)
        except queue.Empty:
            continue

        frames = ring.latest(N_FRAMES)
        if not frames:
            continue

        t0 = time.time()
        behavior, raw = run_inference(model, frames)
        elapsed_ms = (time.time() - t0) * 1000

        label = BEHAVIORS.get(behavior, "정상") if behavior else "정상"
        print(f"[infer] {elapsed_ms:.0f}ms  → {label}", flush=True)

        debug_state.update_inference(label, raw.strip(), elapsed_ms)

        alert = judge.update(behavior)
        if alert:
            send_alert(alert)


# ── GStreamer 파이프라인 ───────────────────────────────────────────────────────

def build_pipeline_str(url: str, target_fps: float) -> str:
    """
    Branch B 파이프라인 문자열 생성.
    videorate로 FPS 정규화: 카메라 원본 FPS(25/30/60)에 무관하게 균일 간격 프레임 추출.
    target_fps = N_FRAMES / inference_interval 로 결정 (OI-02).
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
            print("[ERROR] buffer.map() 실패", flush=True)
            return Gst.FlowReturn.ERROR

        arr = np.frombuffer(map_info.data, dtype=np.uint8).reshape(h, w, 4)
        img = Image.fromarray(arr[:, :, :3], mode='RGB').resize(VLM_INPUT_SIZE)
        buf.unmap(map_info)

        ring.push(img)
        debug_state.update_frame(img, w, h)

        # 추론 큐에 신호 (non-blocking, 추론 중이면 drop)
        try:
            infer_queue.put_nowait(True)
        except queue.Full:
            pass

        return Gst.FlowReturn.OK

    return on_new_sample


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Wally-backend App 시작 ===", flush=True)
    print(f"  MEDIAMTX_URL : {MEDIAMTX_URL}", flush=True)
    print(f"  MODEL_ID     : {MODEL_ID}", flush=True)
    print(f"  TARGET_FPS   : {TARGET_FPS}", flush=True)
    print(f"  N_FRAMES     : {N_FRAMES}", flush=True)
    print(f"  RING_SIZE    : {RING_SIZE}", flush=True)
    print(f"  CONSEC_N     : {CONSEC_N}", flush=True)
    print(f"  FCM_CREDENTIALS : {FCM_CREDENTIALS or '(미설정)'}", flush=True)
    print(f"  FCM_TOKEN       : {'설정됨' if FCM_TOKEN else '(미설정)'}", flush=True)

    # FCM 초기화
    if init_fcm():
        print(f"[init] FCM 활성화: project={_fcm_project_id}", flush=True)
    else:
        print("[init] FCM 비활성화 (FCM_CREDENTIALS 미설정 — 로그 출력만)", flush=True)

    # VLM 모델 로드
    print(f"\n[init] VLM 모델 로드 중: {MODEL_ID}", flush=True)
    t0 = time.time()
    model = NanoLLM.from_pretrained(MODEL_ID, api="mlc", quantization="q4f16_ft")
    print(f"[init] 모델 로드 완료 ({time.time() - t0:.1f}s)", flush=True)

    # 컴포넌트 초기화
    ring     = RingBuffer(maxlen=RING_SIZE)
    judge    = EventJudge()
    infer_q  = queue.Queue(maxsize=1)  # maxsize=1: 추론 중 중복 트리거 방지

    # 디버그 대시보드에 참조 전달
    debug_state.set_refs(ring, RING_SIZE, judge, {
        "target_fps": TARGET_FPS,
        "n_frames": N_FRAMES,
        "consec_n": CONSEC_N,
    })

    # 추론 워커 스레드 시작
    worker = threading.Thread(
        target=inference_worker,
        args=(model, ring, judge, infer_q),
        daemon=True,
    )
    worker.start()

    # GStreamer 파이프라인 초기화
    Gst.init(None)
    pipeline_str = build_pipeline_str(MEDIAMTX_URL, TARGET_FPS)
    print(f"\n[init] Pipeline: {pipeline_str}", flush=True)

    pipeline = Gst.parse_launch(pipeline_str)
    sink = pipeline.get_by_name('sink')
    sink.connect('new-sample', make_frame_callback(ring, infer_q))

    pipeline.set_state(Gst.State.PLAYING)
    print("[init] Pipeline PLAYING\n", flush=True)

    # 디버그 웹서버 시작
    start_debug_server(8080)

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n[main] 종료 신호 수신", flush=True)
    finally:
        pipeline.set_state(Gst.State.NULL)
        print("[main] Pipeline 정지", flush=True)


if __name__ == '__main__':
    main()

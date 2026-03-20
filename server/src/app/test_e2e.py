"""
Wally-backend — E2E 통합 테스트 (비즈니스 로직 레이어)

GStreamer / VLM 없이 아래 흐름을 검증한다:
  EventJudge → send_alert() → preserve_clip() → 클립 파일 생성

VLM + GStreamer 파이프라인은 test_vlm_pipeline.py 에서 이미 검증 완료.
실 카메라 종단 테스트는 main.py 를 직접 구동해 로그로 확인한다.

실행 (app 컨테이너 내부 또는 호스트):
  python /app/test_e2e.py
"""

import os
import shutil
import sys
import tempfile
import time

# ── 임시 녹화 디렉토리를 환경변수로 주입 (테스트 격리) ────────────────────────
# main.py 는 모듈 임포트 시 환경변수로 상수를 확정하므로, import 전에 설정해야 함.

_tmp = tempfile.mkdtemp(prefix="wally_backend_test_")
_RECORDINGS_DIR = os.path.join(_tmp, "live")
_EVENTS_DIR     = os.path.join(_tmp, "events")
os.makedirs(_RECORDINGS_DIR)

os.environ["RECORDINGS_DIR"]    = _RECORDINGS_DIR
os.environ["EVENTS_DIR"]        = _EVENTS_DIR
os.environ["CLIP_PRE_SEGMENTS"] = "2"
os.environ["CONSEC_N"]          = "3"

# main.py 모듈 임포트 (GStreamer / NanoLLM 은 사용하지 않으므로 gi / nano_llm 없어도 됨)
# 단, import 시 gi.require_version 이 실행되므로 GStreamer 설치 환경에서 실행할 것.
import main as _main  # noqa: E402
from main import EventJudge, preserve_clip, send_alert, BEHAVIORS  # noqa: E402

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

results = []


def check(name: str, condition: bool) -> None:
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}", flush=True)
    results.append((name, condition))


# ── 1. EventJudge 동작 검증 ───────────────────────────────────────────────────

print("\n[1/3] EventJudge 동작 검증")

judge = EventJudge(consec_n=3)

# 1-1. CONSEC_N 미만: 알림 없음
for _ in range(2):
    alert = judge.update("scratching")
check("CONSEC_N 미만(2회)은 알림 없음", alert is None)

# 1-2. CONSEC_N 도달: 알림 발령
alert = judge.update("scratching")
check("CONSEC_N 도달(3회)에 알림 발령", alert == "scratching")

# 1-3. 발령 직후 streak 초기화: 다음 1회는 알림 없음
alert = judge.update("scratching")
check("발령 후 streak 초기화 (1회 추가 → 알림 없음)", alert is None)

# 1-4. 다른 행동 감지 시 streak 초기화
judge2 = EventJudge(consec_n=3)
judge2.update("scratching")
judge2.update("scratching")
alert = judge2.update("circling")   # 다른 행동
check("다른 행동 감지 시 streak 초기화", alert is None)
alert = judge2.update("scratching")  # 다시 scratching 1회 — 아직 2회 미만
check("streak 초기화 후 1회: 알림 없음", alert is None)

# 1-5. None(정상) 감지 시 streak 초기화
judge3 = EventJudge(consec_n=3)
judge3.update("vomiting")
judge3.update("vomiting")
alert = judge3.update(None)          # NORMAL
check("NORMAL 감지 시 streak 초기화", alert is None)


# ── 2. preserve_clip 동작 검증 ────────────────────────────────────────────────

print("\n[2/3] preserve_clip 동작 검증")

# 더미 세그먼트 파일 생성 (비어있는 .mp4 파일)
seg_names = [
    "2026-03-17_10-00-00.mp4",
    "2026-03-17_10-01-00.mp4",
    "2026-03-17_10-02-00.mp4",
]
for i, name in enumerate(seg_names):
    path = os.path.join(_RECORDINGS_DIR, name)
    with open(path, "wb") as f:
        f.write(b"\x00" * 1024)  # 1KB 더미
    # mtime 차이를 두어 정렬 결과 예측 가능하게
    os.utime(path, (time.time() - (len(seg_names) - i) * 10, time.time() - (len(seg_names) - i) * 10))

event_time = time.time()
preserve_clip("scratching", event_time)

ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(event_time))
event_dir_name = f"{ts}_scratching"
event_dir = os.path.join(_EVENTS_DIR, event_dir_name)

check("이벤트 디렉토리 생성됨", os.path.isdir(event_dir))

copied = os.listdir(event_dir) if os.path.isdir(event_dir) else []
check(f"세그먼트 {min(2, len(seg_names))}개 복사됨 (실제: {len(copied)}개)", len(copied) == 2)

# 복사된 파일이 가장 최신 2개인지 확인 (mtime 기준)
expected_latest = sorted(seg_names, reverse=True)[:2]
check("최신 2개 세그먼트가 복사됨", set(copied) == set(expected_latest))

# 2-2. 세그먼트 없는 경우 → 오류 없이 처리 (모듈 상수를 직접 패치)
orig_recordings_dir = _main.RECORDINGS_DIR
empty_dir = os.path.join(_tmp, "empty_live")
os.makedirs(empty_dir)
_main.RECORDINGS_DIR = empty_dir
try:
    preserve_clip("vomiting", time.time())  # 파일 없음 → 오류 없이 리턴
    check("세그먼트 없을 때 오류 없이 처리", True)
except Exception as e:
    check(f"세그먼트 없을 때 오류 없이 처리 (예외: {e})", False)
finally:
    _main.RECORDINGS_DIR = orig_recordings_dir


# ── 3. send_alert 흐름 검증 (FCM 비활성화 상태) ──────────────────────────────

print("\n[3/3] send_alert 흐름 검증 (FCM 비활성화)")

# FCM 미설정 상태에서 send_alert → 로그 출력 + preserve_clip 호출 후 오류 없어야 함
try:
    send_alert("circling")
    time.sleep(0.2)  # preserve_clip 스레드 완료 대기
    check("send_alert 오류 없이 완료 (FCM 비활성화)", True)
except Exception as e:
    check(f"send_alert 오류 없이 완료 (예외: {e})", False)

# circling 이벤트 디렉토리 생성 확인
events = os.listdir(_EVENTS_DIR) if os.path.isdir(_EVENTS_DIR) else []
circling_events = [d for d in events if "circling" in d]
check("send_alert → preserve_clip 클립 생성 확인", len(circling_events) >= 1)


# ── 결과 요약 ─────────────────────────────────────────────────────────────────

print()
print("=" * 50)
print("  E2E 테스트 결과 요약")
print("=" * 50)
total  = len(results)
passed = sum(1 for _, ok in results if ok)
for name, ok in results:
    print(f"  [{'OK' if ok else 'NG'}] {name}")
print()
print(f"  {passed} / {total} 통과")
print()

shutil.rmtree(_tmp)  # 임시 디렉토리 정리

if passed < total:
    sys.exit(1)

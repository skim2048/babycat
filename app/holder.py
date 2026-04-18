"""
VLM 홀더 싱글톤 + 전환 요청 검증.

main.py는 컨테이너에서 `python main.py`로 실행되어 __main__ 모듈이 된다.
server.py가 `from main import ...` 하면 Python이 main.py를 `main`이라는
별도 모듈로 다시 로드하여 전역 상태가 분리된다. 이 모듈은 양쪽이 공유하는
단일 진입점을 제공해 그 함정을 피한다.

계약: `_available_models` 는 main._precompile_all 이 끝난 뒤 set_available()
로만 채워진다. 그 전에 request_switch 가 불리면 어떤 모델이든 거절된다.
"""

import os

_DEFAULT = "Efficient-Large-Model/VILA1.5-3b"
VLM_MODELS = [m.strip() for m in os.getenv("VLM_MODELS", _DEFAULT).split(",") if m.strip()]
if not VLM_MODELS:
    VLM_MODELS = [_DEFAULT]

_holder = None
_available_models: list[str] = []  # precompile 완료 후 main이 set_available()로 채운다.


def set_holder(h) -> None:
    global _holder
    _holder = h


def set_available(models: list[str]) -> None:
    global _available_models
    _available_models = list(models)


def request_switch(name: str) -> tuple[bool, str]:
    """
    서버 핸들러에서 호출. (accepted, reason) 반환.
    accepted=True 이면 곧 추론 워커가 전환을 수행한다.
    """
    if _holder is None:
        return False, "model not loaded yet"
    if not _available_models:
        return False, "models not ready yet"
    if name not in _available_models:
        return False, "model not available (not precompiled)"
    _holder.request_switch(name)
    return True, "queued"

"""
VLM holder singleton and switch-request validation.

When the container runs `python main.py`, `main.py` becomes the `__main__`
module. If `server.py` does `from main import ...`, Python re-loads
`main.py` as a separate module named `main`, splitting the global state
across two module objects. This module is the single entry point both
sides share, which avoids that pitfall.

Contract: `_available_models` is populated only by `set_available()`
after `main._precompile_all` finishes. Any `request_switch` call before
that point is rejected regardless of the requested model.

@claude
"""

import os

_DEFAULT = "Efficient-Large-Model/VILA1.5-3b"
VLM_MODELS = [m.strip() for m in os.getenv("VLM_MODELS", _DEFAULT).split(",") if m.strip()]
if not VLM_MODELS:
    VLM_MODELS = [_DEFAULT]

_holder = None
# @claude Filled in by main via set_available() once precompilation finishes.
_available_models: list[str] = []


def set_holder(h) -> None:
    global _holder
    _holder = h


def set_available(models: list[str]) -> None:
    global _available_models
    _available_models = list(models)


def request_switch(name: str) -> tuple[bool, str]:
    """
    Called from the HTTP handler. Returns (accepted, reason); when
    accepted=True the inference worker will perform the switch shortly.

    @claude
    """
    if _holder is None:
        return False, "model not loaded yet"
    if not _available_models:
        return False, "models not ready yet"
    if name not in _available_models:
        return False, "model not available (not precompiled)"
    _holder.request_switch(name)
    return True, "queued"

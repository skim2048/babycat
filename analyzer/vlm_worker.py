"""
VLM model subprocess isolation.

NanoLLM / MLC (TVM) / clip_trt (TensorRT) do not reliably release
CUDA/TVM/TensorRT memory when a model is dropped in-process: `gc.collect()`
reclaims only the Python wrapper, not the native allocations underneath.
On Jetson Orin NX, where GPU and CPU share one unified memory pool, that
leftover native memory shows up as ever-growing RAM after each switch.

This module runs the live VLM in a dedicated child process. A switch
terminates the child and spawns a fresh one for the target model; the OS
reclaims all CUDA/TVM/TensorRT memory on child exit — the same reasoning
`main._precompile_one` already relies on for sequential compilation.

Layout:
  - parent: imports `VlmProcess`; keeps GStreamer, the ring buffer and
    the HTTP server. It never imports nano_llm and never touches CUDA.
  - child : `python3 vlm_worker.py <model_id> <ipc_addr>`; imports
    nano_llm, owns the model, serves one inference at a time.

IPC is a `multiprocessing.connection` AF_UNIX channel carrying pickled
messages. The child creates the listener so the parent can poll the
child's liveness while connecting (no blocking accept on a dead child).

@claude
"""

import logging
import os
import secrets
import subprocess
import sys
import time
from multiprocessing.connection import Client, Listener

log = logging.getLogger(__name__)

# @claude Model load against a warm .so cache (precompile guarantees the cache
# @claude exists before any live child is spawned). Generous ceiling for 13b.
LOAD_TIMEOUT = float(os.getenv("VLM_LOAD_TIMEOUT", "1800"))
# @claude One generate() call — a cold 13b on Orin NX is slow but not this slow.
INFER_TIMEOUT = float(os.getenv("VLM_INFER_TIMEOUT", "120"))
# @claude Upper bound on tokens per VLM generation. Stop markers (</s>, <|im_end|>,
# @claude etc.) may truncate earlier; see _child_run_inference.
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "32"))
# @claude SIGTERM → SIGKILL grace when stopping a child.
STOP_GRACE = 10.0
# @claude Bound on how long the parent waits for the child to open its listener.
CONNECT_TIMEOUT = 60.0

_AUTHKEY_ENV = "VLM_IPC_AUTHKEY"


# ── Child side ───────────────────────────────────────────────────────────────

def _child_run_inference(model, ChatHistory, frames, prompt):
    """
    Run VLM inference over a list of PIL frames using the ChatHistory API.
    chat.reset() and gc.collect() are mandatory — see NanoLLM GitHub
    issue #39 on memory leaks. (Moved verbatim from main.run_inference.)

    @claude
    """
    import gc

    chat = ChatHistory(model)
    for img in frames:
        chat.append('user', image=img)
    chat.append('user', text=prompt)

    embedding, _ = chat.embed_chat()
    tokens = []
    for token in model.generate(embedding, max_new_tokens=MAX_NEW_TOKENS, streaming=True):
        tokens.append(token)

    raw = "".join(tokens)
    # @claude Truncate at any stop token (vicuna-v1 </s>, ChatML <|im_end|>) and at common
    # @claude roleplay artifacts (###, <|im_start|>, assistant:, user:) when they appear.
    for marker in ("<|im_end|>", "</s>", "<|im_start|>", "###", "assistant:", "user:"):
        idx = raw.find(marker)
        if idx >= 0:
            raw = raw[:idx]
    raw = raw.strip()
    chat.reset()
    gc.collect()
    return raw


def _child_main(model_id: str, ipc_addr: str) -> None:
    """
    Child entry point. Opens the IPC listener, waits for the parent to
    connect, loads `model_id`, then serves one inference per
    ("infer", (frames, prompt)) message until the parent disconnects.

    Protocol (child → parent): ("ready", None) | ("load_error", str)
                               ("result", str) | ("infer_error", str)
    Protocol (parent → child): ("infer", (frames, prompt))

    @claude
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [vlm_worker] %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    authkey = bytes.fromhex(os.environ[_AUTHKEY_ENV])
    listener = Listener(ipc_addr, family="AF_UNIX", authkey=authkey)
    try:
        conn = listener.accept()
    finally:
        # @claude Unlink the socket file once the single expected client is in.
        listener.close()

    try:
        try:
            from nano_llm import NanoLLM, ChatHistory
            t0 = time.time()
            model = NanoLLM.from_pretrained(model_id, api="mlc", quantization="q4f16_ft")
            log.info("model loaded (%.1fs): %s", time.time() - t0, model_id)
        except Exception as e:
            conn.send(("load_error", repr(e)))
            return
        conn.send(("ready", None))

        while True:
            try:
                kind, payload = conn.recv()
            except (EOFError, OSError):
                break  # @claude Parent closed the connection — exit so the OS reclaims memory.
            if kind != "infer":
                continue
            frames, prompt = payload
            try:
                text = _child_run_inference(model, ChatHistory, frames, prompt)
                conn.send(("result", text))
            except Exception as e:
                log.error("inference failed: %s", e)
                conn.send(("infer_error", repr(e)))
    finally:
        conn.close()


# ── Parent side ──────────────────────────────────────────────────────────────

def _hard_stop(proc: subprocess.Popen) -> None:
    """SIGTERM, then SIGKILL after STOP_GRACE. Blocks until the child is dead. @claude"""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=STOP_GRACE)
    except subprocess.TimeoutExpired:
        log.warning("VLM child %d ignored SIGTERM — sending SIGKILL", proc.pid)
        proc.kill()
        try:
            proc.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            log.error("VLM child %d unkillable", proc.pid)
            return
    log.info("VLM child %d stopped (exit code %s)", proc.pid, proc.returncode)


def _connect(addr: str, authkey: bytes, proc: subprocess.Popen):
    """
    Connect to the child's listener, retrying until it is up. Fails fast
    if the child exits before opening the socket.

    @claude
    """
    deadline = time.time() + CONNECT_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"child exited before IPC connect (exit code {proc.returncode})")
        try:
            return Client(addr, family="AF_UNIX", authkey=authkey)
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(0.1)
    raise RuntimeError(f"child did not open IPC socket within {CONNECT_TIMEOUT:.0f}s")


class VlmProcess:
    """
    Parent-side manager for the VLM child process. Owns exactly one child
    at a time; a switch kills the old child (freeing its native memory)
    before spawning the new one.

    Not thread-safe: every method is called from the single inference
    worker thread. The cross-thread switch *request* is mediated
    separately by main.ModelHolder.

    @claude
    """

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._conn = None
        self._current: str | None = None

    @property
    def current(self) -> str | None:
        """The model id of the running child, or None if none has loaded. @claude"""
        return self._current

    def is_ready(self) -> bool:
        """True when a child is alive and connected. @claude"""
        return self._conn is not None and self._proc is not None and self._proc.poll() is None

    def start(self, model_id: str) -> None:
        """Spawn a child for `model_id`; block until it reports ready. @claude"""
        self._spawn(model_id)

    def switch(self, model_id: str) -> None:
        """
        Kill the current child and spawn one for `model_id`. The OS
        reclaims the old model's CUDA/TVM/TensorRT memory on child exit.

        @claude
        """
        self.stop()
        self._spawn(model_id)

    def infer(self, frames: list, prompt: str) -> str:
        """
        Run one inference in the child. Respawns a crashed child (same
        model) before sending the job. Raises RuntimeError on failure or
        timeout; the next call then starts from a clean respawn.

        @claude
        """
        if not self.is_ready():
            if self._current is None:
                raise RuntimeError("VLM child never started")
            log.warning("VLM child not alive — respawning %s", self._current)
            self._spawn(self._current)
        try:
            self._conn.send(("infer", (frames, prompt)))
            kind, payload = self._recv(INFER_TIMEOUT)
        except Exception as e:
            # @claude Transport broke (timeout / child died mid-job). Drop the
            # @claude child so the next infer() starts from a clean respawn.
            self.stop()
            raise RuntimeError(f"VLM inference transport error: {e}") from e
        if kind == "result":
            return payload
        raise RuntimeError(f"VLM inference error: {payload}")

    def stop(self) -> None:
        """Disconnect and terminate the child if running. Idempotent. @claude"""
        if self._conn is not None:
            try:
                self._conn.close()  # @claude Child sees EOF and exits on its own.
            except Exception:
                pass
            self._conn = None
        if self._proc is not None:
            _hard_stop(self._proc)
            self._proc = None

    # ── internals ────────────────────────────────────────────────────────────

    def _spawn(self, model_id: str) -> None:
        """
        Launch a child for `model_id` and block until it reports ready.
        Leaves the manager stopped (and raises) on any failure.

        @claude
        """
        addr = f"/tmp/babycat-vlm-{os.getpid()}-{secrets.token_hex(4)}.sock"
        authkey = secrets.token_bytes(32)
        env = {**os.environ, _AUTHKEY_ENV: authkey.hex()}

        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), model_id, addr],
            env=env,
        )
        self._proc = proc
        self._conn = None
        log.info("VLM child started (pid=%d): %s", proc.pid, model_id)

        t0 = time.time()
        try:
            self._conn = _connect(addr, authkey, proc)
            kind, payload = self._recv(LOAD_TIMEOUT)
        except Exception as e:
            self.stop()
            raise RuntimeError(f"VLM child load failed ({model_id}): {e}") from e
        if kind != "ready":
            self.stop()
            raise RuntimeError(f"VLM child load failed ({model_id}): {payload}")

        self._current = model_id
        log.info("VLM child ready (%.1fs): %s", time.time() - t0, model_id)

    def _recv(self, timeout: float):
        """
        Receive one IPC message, failing fast if the child dies. Polls in
        1s slices so a crashed child is detected within ~1s instead of
        blocking for the full timeout.

        @claude
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._conn.poll(1.0):
                return self._conn.recv()
            if self._proc.poll() is not None:
                raise RuntimeError(f"child exited (exit code {self._proc.returncode})")
        raise RuntimeError(f"IPC receive timed out after {timeout:.0f}s")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: vlm_worker.py <model_id> <ipc_addr>", file=sys.stderr)
        sys.exit(2)
    _child_main(sys.argv[1], sys.argv[2])

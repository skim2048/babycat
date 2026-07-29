"""
Internal relays: JSON forwarding and stream relays (SSE, MJPEG, HLS, WHEP).

Internal calls carry no authentication — the router already verified the
request, and the compose network is inside the trust boundary (SDD §6.3).

@claude
"""

import json
import time
import urllib.error
import urllib.request

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

# @claude Hop-by-hop headers must not be copied through a relay.
_SKIP_HEADERS = {
    "connection", "keep-alive", "transfer-encoding", "content-encoding",
    "content-length", "server", "date",
}


def _target_url(base: str, path: str, query: str | None) -> str:
    url = f"{base}{path}"
    if query:
        url = f"{url}?{query}"
    return url


def forward_json(
    base: str,
    method: str,
    path: str,
    body: dict | None = None,
    query: str | None = None,
    timeout: int = 10,
) -> JSONResponse:
    """Forward a JSON request and return the upstream response as-is.
    Upstream 5xx and transport failures are normalized to 502 (SDD §6.5)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(_target_url(base, path, query), data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        status = e.code
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
    if status >= 500:
        raise HTTPException(status_code=502, detail="upstream error")
    return JSONResponse(status_code=status, content=json.loads(text) if text else None)


def relay_stream(
    base: str,
    path: str,
    query: str | None = None,
    stop_when=None,
    stop_check_interval: float = 2.0,
) -> StreamingResponse:
    """
    Relay an unbounded upstream response (SSE, MJPEG) chunk by chunk. No
    read timeout: these responses stay open by design, and an idle SSE
    channel must not be mistaken for a stalled one.

    stop_when: optional predicate evaluated at most once per
    stop_check_interval seconds between chunks; a truthy result ends the
    relay (FR-047 closes streams when the session is replaced).
    """
    req = urllib.request.Request(_target_url(base, path, query), method="GET")
    try:
        upstream = urllib.request.urlopen(req, timeout=None)
    except urllib.error.HTTPError as e:
        e.close()
        raise HTTPException(status_code=e.code, detail="upstream rejected the request")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")

    def iterate():
        # @claude read1() returns as soon as any bytes arrive, so an SSE event
        # @claude is forwarded when produced, not once a buffer fills.
        last_check = time.monotonic()
        try:
            while True:
                chunk = upstream.read1(8192)
                if not chunk:
                    break
                if stop_when is not None:
                    now = time.monotonic()
                    if now - last_check >= stop_check_interval:
                        last_check = now
                        if stop_when():
                            break
                yield chunk
        finally:
            upstream.close()

    return StreamingResponse(
        iterate(),
        media_type=upstream.headers.get("Content-Type", "application/octet-stream"),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _blocking_fetch(url: str, method: str, body: bytes, headers: dict, timeout: int):
    req = urllib.request.Request(url, data=body if body else None, method=method)
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        upstream = urllib.request.urlopen(req, timeout=timeout)
        status = upstream.status
    except urllib.error.HTTPError as e:
        upstream = e
        status = e.code
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")

    out_headers = {}
    for name, value in upstream.headers.items():
        if name.lower() in _SKIP_HEADERS:
            continue
        out_headers[name] = value
    content = upstream.read()
    upstream.close()
    return status, out_headers, content


async def relay_raw(request: Request, base: str, path: str, timeout: int = 15) -> Response:
    """
    Byte-level relay preserving method, body, Range, content type, and the
    upstream status and headers. Used for clip playback (Range) and for
    the HLS/WHEP paths (SDD §6.4 (2)); a path-form Location header passes
    through unchanged, which keeps WHEP session resources on router paths.

    The blocking transfer runs in the threadpool so the event loop stays
    responsive. Bodies are buffered whole — clips are seconds long and HLS
    segments are small, so this stays within reason on a LAN.
    """
    body = await request.body()
    headers = {}
    for name in ("Content-Type", "Range", "Accept", "If-Match"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    from fastapi.concurrency import run_in_threadpool
    status, out_headers, content = await run_in_threadpool(
        _blocking_fetch,
        _target_url(base, path, request.url.query or None),
        request.method, body, headers, timeout,
    )
    return Response(content=content, status_code=status, headers=out_headers)

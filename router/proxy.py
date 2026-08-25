"""
Internal relays: JSON forwarding and stream relays (SSE, MJPEG, HLS, WHEP).

Internal calls carry no authentication — the router already verified the
request, and the compose network is inside the trust boundary (SDD §6.3).

@claude
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException, Request
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

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


def _strip_token(query: str | None) -> str | None:
    """Drop the ?token= credential before relaying (SDD §4.1): the fallback
    exists for the router's own authentication, and an upstream access log
    must not end up holding live tokens. @claude"""
    if not query:
        return None
    kept = [(k, v) for k, v in urllib.parse.parse_qsl(query, keep_blank_values=True) if k != "token"]
    return urllib.parse.urlencode(kept) or None


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
    try:
        content = json.loads(text) if text else None
    except ValueError:
        # @claude A non-JSON body (e.g. a framework's plain-text 4xx) is still
        # @claude passed through with its meaning intact (SDD §6.5).
        content = {"detail": text}
    return JSONResponse(status_code=status, content=content)


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


def _blocking_open(url: str, method: str, body: bytes, headers: dict, timeout: int):
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
    return status, out_headers, upstream


def _iter_body(upstream):
    try:
        while True:
            chunk = upstream.read(65536)
            if not chunk:
                break
            yield chunk
    finally:
        upstream.close()


async def relay_raw(request: Request, base: str, path: str, timeout: int = 15) -> StreamingResponse:
    """
    Byte-level relay preserving method, body, Range, content type, and the
    upstream status and headers. Used for clip playback (Range) and for
    the HLS/WHEP paths (SDD §6.4 (2)). MediaMTX's WHEP Location header is
    path-form (/live/whep/<id>) and the router serves the same path, so it
    passes through unchanged.

    The body is forwarded as it arrives (SDD §6.4 (2)): the upstream is
    opened in the threadpool and its chunks are read there too, so neither
    a multi-second clip nor a slow segment blocks the event loop or is held
    in memory whole.
    """
    body = await request.body()
    headers = {}
    for name in ("Content-Type", "Range", "Accept", "If-Match"):
        value = request.headers.get(name)
        if value:
            headers[name] = value
    status, out_headers, upstream = await run_in_threadpool(
        _blocking_open,
        _target_url(base, path, _strip_token(request.url.query)),
        request.method, body, headers, timeout,
    )
    media_type = out_headers.pop("Content-Type", None)
    return StreamingResponse(
        iterate_in_threadpool(_iter_body(upstream)),
        status_code=status, headers=out_headers, media_type=media_type,
    )

"""One log line for every HTTP request the Web process answers.

The browser's own network panel is not visible in an incident, so each request
leaves one line naming the method, the target, the status, how long it took,
and how many bytes came back. The middleware is pure ASGI: it observes the
response frames instead of buffering them, so streamed turns keep streaming and
an upload body is never copied.

Requests that repeat on a timer would drown that file, so a path prefix may
declare a sample rate: it logs its first request and every Nth one after that,
and reports how many requests the line stands for. ``settings
.access_log_sample_rates`` holds the rules (default ``/api/health=100``), and
everything unmatched logs every request.

Query *values* are deliberately left out. Endpoints such as the channel login
poll carry a pairing code in the query string, and an access log is not the
place to keep a copy of it; the parameter names still say what the request did.
"""

import asyncio
from collections.abc import Mapping
from time import monotonic

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ...config import settings
from ...infra.log import get_logger, log_preview

logger = get_logger(__name__)

#: Rate used for a path no configured prefix matches: log every request.
DEFAULT_SAMPLE_RATE = 1


class RequestLogMiddleware:
    """Log the outcome of every HTTP request without touching its payload."""

    def __init__(self, app: ASGIApp, *, sample_rates: Mapping[str, int] | None = None) -> None:
        self.app = app
        self.sample_rates = dict(sample_rates if sample_rates is not None else settings.access_log_sample_rates)
        self._seen: dict[str, int] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = monotonic()
        status = 500
        sent = 0
        method = scope.get("method", "")
        target = _target(scope)
        client = _client(scope)
        rate, seen = self._sample(scope.get("path") or "/")
        report = rate <= DEFAULT_SAMPLE_RATE or seen == 1 or seen % rate == 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status, sent
            if message["type"] == "http.response.start":
                status = int(message["status"])
            elif message["type"] == "http.response.body":
                sent += len(message.get("body") or b"")
            await send(message)

        try:
            # A sampled request still has to run and still reports its own
            # failures; only its success line is dropped.
            await self.app(scope, receive, send_wrapper if report else send)
        except asyncio.CancelledError:
            logger.warning(
                "Request cancelled; method=%s target=%s duration_ms=%.0f client=%s sampled=%d",
                method,
                target,
                _elapsed_ms(started),
                client,
                seen,
            )
            raise
        except Exception as error:
            logger.warning(
                "Request failed; method=%s target=%s duration_ms=%.0f client=%s sampled=%d error=%s",
                method,
                target,
                _elapsed_ms(started),
                client,
                seen,
                log_preview(f"{type(error).__name__}: {error}"),
            )
            raise
        if not report:
            return
        logger.info(
            "Request; method=%s target=%s status=%d bytes=%d duration_ms=%.0f client=%s sampled=%d",
            method,
            target,
            status,
            sent,
            _elapsed_ms(started),
            client,
            seen,
        )

    def _sample(self, path: str) -> tuple[int, int]:
        """Count one request and return the rate that matched it and its count."""
        for prefix, rate in self.sample_rates.items():
            if path.startswith(prefix):
                seen = self._seen[prefix] = self._seen.get(prefix, 0) + 1
                return rate, seen
        return DEFAULT_SAMPLE_RATE, 1


def _elapsed_ms(started: float) -> float:
    return (monotonic() - started) * 1_000


def _target(scope: Scope) -> str:
    """Return the request path plus the query parameter names it carried."""
    path = scope.get("path") or "/"
    raw_query = scope.get("query_string") or b""
    if not raw_query:
        return path
    names = [part.partition(b"=")[0].decode("utf-8", "replace") for part in raw_query.split(b"&") if part]
    return f"{path}?{','.join(names)}" if names else path


def _client(scope: Scope) -> str:
    """Return the peer address, which is absent for some in-process callers."""
    client = scope.get("client")
    return f"{client[0]}:{client[1]}" if client else "unknown"


__all__ = ["DEFAULT_SAMPLE_RATE", "RequestLogMiddleware"]

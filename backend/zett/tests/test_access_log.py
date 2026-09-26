"""Access-log sampling for paths that repeat on a timer."""

from collections.abc import Awaitable, Callable

from zett.application.api.access_log import RequestLogMiddleware
from zett.config import parse_access_log_sample_rates

Send = Callable[[dict], Awaitable[None]]


class _RecordingApp:
    """Minimal ASGI app that answers one fixed response."""

    def __init__(self, *, status: int = 200, fail: bool = False) -> None:
        self.status = status
        self.fail = fail
        self.calls = 0

    async def __call__(self, scope: dict, receive: Callable, send: Send) -> None:
        del scope, receive
        self.calls += 1
        if self.fail:
            raise RuntimeError("handler exploded")
        await send({"type": "http.response.start", "status": self.status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _scope(path: str) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "client": ("127.0.0.1", 41234),
        "headers": [],
    }


async def _receive() -> dict:
    return {"type": "http.request", "body": b""}


async def _send(message: dict) -> None:
    del message


def test_sample_rate_rules_ignore_broken_entries() -> None:
    assert parse_access_log_sample_rates("/api/health=100") == {"/api/health": 100}
    assert parse_access_log_sample_rates("/api/health=100,/api/files=20") == {
        "/api/health": 100,
        "/api/files": 20,
    }
    assert parse_access_log_sample_rates("/api/health,/api/files=x,/api/tags=0,") == {}


async def test_a_sampled_path_logs_its_first_request_then_every_nth(captured_logs) -> None:
    app = _RecordingApp()
    middleware = RequestLogMiddleware(app, sample_rates={"/api/health": 3})

    for _ in range(7):
        await middleware(_scope("/api/health/processes/heartbeat"), _receive, _send)

    assert app.calls == 7
    lines = [message for message in captured_logs if "Request;" in message]
    assert [line.rsplit("sampled=", 1)[1] for line in lines] == ["1", "3", "6"]
    assert all("target=/api/health/processes/heartbeat" in line for line in lines)


async def test_every_unmatched_path_is_logged(captured_logs) -> None:
    app = _RecordingApp()
    middleware = RequestLogMiddleware(app, sample_rates={"/api/health": 100})

    for _ in range(3):
        await middleware(_scope("/api/agent/sessions"), _receive, _send)

    lines = [message for message in captured_logs if "Request;" in message]
    assert len(lines) == 3
    assert all(line.endswith("sampled=1") for line in lines)


async def test_a_sampled_out_request_still_logs_its_failure(captured_logs) -> None:
    """Sampling must not hide an error; only its success lines are dropped."""
    app = _RecordingApp(fail=True)
    middleware = RequestLogMiddleware(app, sample_rates={"/api/health": 100})

    for _ in range(3):
        try:
            await middleware(_scope("/api/health/processes/heartbeat"), _receive, _send)
        except RuntimeError:
            continue

    failures = [message for message in captured_logs if "Request failed" in message]
    assert len(failures) == 3
    assert all("handler exploded" in message for message in failures)


async def test_the_default_rule_samples_the_health_endpoints() -> None:
    middleware = RequestLogMiddleware(_RecordingApp())

    assert middleware.sample_rates == {"/api/health": 100}
    assert middleware._sample("/api/health/processes/heartbeat") == (100, 1)
    assert middleware._sample("/api/agent/sessions") == (1, 1)

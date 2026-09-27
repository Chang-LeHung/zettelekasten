"""Call a running Zett server over HTTP with nothing but the standard library.

Commands that only need the API stay out of the application's import graph
this way: they read the address the runtime state file records, send one
request, and print the answer, so no FastAPI, SQLAlchemy, or agent runtime is
imported to talk to a server that already has them.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any


class ServerUnavailableError(RuntimeError):
    """Raised when the recorded server cannot be reached."""


class ServerRequestError(RuntimeError):
    """Raised when the server answers a request with a failure."""


def recorded_url() -> str:
    """Return the base URL of the server this installation recorded."""
    from ..application.runtime import RuntimeService

    report = asyncio.run(RuntimeService().status())
    if not report.running or report.url is None:
        raise ServerUnavailableError("Zett is not running; start it with `zett start`")
    return report.url


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    base_url: str | None = None,
    timeout: float = 60.0,
) -> Any:
    """Send one JSON request and return its decoded body."""
    url = f"{base_url or recorded_url()}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, method=method, headers=headers),
            timeout=timeout,
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ServerRequestError(f"{error.code} {error.reason}: {_detail(error)}") from error
    except urllib.error.URLError as error:
        raise ServerUnavailableError(f"Could not reach the Zett server at {url}: {error.reason}") from error
    return json.loads(body) if body else None


def _detail(error: urllib.error.HTTPError) -> str:
    """Return the server's error detail, falling back to the status text."""
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (ValueError, OSError):
        return str(error.reason)
    if isinstance(payload, dict) and isinstance(detail := payload.get("detail"), str):
        return detail
    return json.dumps(payload, ensure_ascii=False)

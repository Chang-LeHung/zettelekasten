"""Start, inspect, and describe the local Zett server process.

``zett start`` detaches the server by default and returns when it answers, and
``zett status`` reports what the runtime state file records. Both are
orchestration over the same two adapters: the runtime process controller that
owns ``runtime.json`` and the launcher that spawns a detached CLI process.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ...config import settings
from ...infra.log import get_logger
from ...infra.scheduler import process_platform
from ...infra.scheduler.runtime_state import RuntimeProcessController
from ...schemas import RuntimeStatus, ServerStartResult

if TYPE_CHECKING:
    from ...infra.scheduler.processes import BackgroundServerProcess

logger = get_logger(__name__)

#: Lines of the detached console log reprinted when startup fails.
START_FAILURE_LOG_LINES = 20


class BackgroundStartError(RuntimeError):
    """Raised when a detached server does not become ready."""


class RuntimeService:
    """Coordinate the local server process for the CLI."""

    def __init__(
        self,
        *,
        controller: RuntimeProcessController | None = None,
        launcher: Callable[..., BackgroundServerProcess] | None = None,
        timeout_seconds: float = settings.background_start_timeout_seconds,
        poll_seconds: float = 0.2,
    ) -> None:
        # The launcher lives with the scheduler adapters and pulls in httpx it
        # does not need for `zett status`, so it is resolved where it is used.
        self.controller = controller or RuntimeProcessController()
        self.launcher = launcher
        self.timeout_seconds = max(0.1, timeout_seconds)
        self.poll_seconds = max(0.01, poll_seconds)

    async def start_in_background(self, *, host: str, port: int, reload: bool) -> ServerStartResult:
        """Detach a server process and wait until it answers on its port.

        Startup conflicts are rejected before anything is spawned, so a second
        ``zett start`` reports the running server instead of leaving two of
        them racing for the port. A child that dies or never binds is stopped
        and reported with the tail of its console log, because a detached
        process has no other way to explain itself.
        """
        from ...infra.scheduler.processes import BACKGROUND_LOG_FILE_NAME, launch_background_server

        await self.controller.prepare_start(port=port)
        log_path = settings.log_directory / BACKGROUND_LOG_FILE_NAME
        try:
            launcher = self.launcher or launch_background_server
            launched = launcher(host=host, port=port, reload=reload, log_path=log_path)
        except OSError as error:
            raise BackgroundStartError(f"Could not start the background server: {error}") from error
        if not await self._wait_until_ready(launched, port):
            _terminate_quietly(launched.pid)
            raise BackgroundStartError(_failure_message(launched, port, self.timeout_seconds))
        logger.info("Zett server detached; pid=%d port=%d log_file=%s", launched.pid, port, log_path)
        return ServerStartResult(
            pid=launched.pid,
            port=port,
            url=f"http://{process_platform.dialable_host(host)}:{port}",
            log_path=str(log_path),
        )

    async def status(self) -> RuntimeStatus:
        """Report the recorded server and child processes.

        ``runtime.json`` plus PID liveness is the whole answer: it is the same
        file ``zett stop`` acts on, so status never describes a server the stop
        command would not.
        """
        return await self.controller.status()

    async def _wait_until_ready(self, launched: BackgroundServerProcess, port: int) -> bool:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if process_platform.port_is_open(port):
                return True
            if not launched.is_running():
                return False
            await asyncio.sleep(self.poll_seconds)
        return process_platform.port_is_open(port)


def _failure_message(launched: BackgroundServerProcess, port: int, timeout_seconds: float) -> str:
    """Explain a failed detached start with the child's own last log lines."""
    lines = [f"Zett did not start in the background on port {port} within {timeout_seconds:g}s."]
    lines.append(f"Process {launched.pid} is {'still running' if launched.is_running() else 'no longer running'}.")
    tail = _log_tail(launched.log_path)
    if tail:
        lines.append(f"Last lines of {launched.log_path}:")
        lines.extend(tail)
    else:
        lines.append(f"No output was written to {launched.log_path}.")
    return "\n".join(lines)


def _log_tail(path: Path, *, lines: int = START_FAILURE_LOG_LINES) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in content.splitlines() if line.strip()][-lines:]


def _terminate_quietly(pid: int) -> None:
    """Stop a failed detached child, ignoring one that already exited."""
    try:
        process_platform.terminate_process(pid, force=False)
    except ProcessLookupError:
        return

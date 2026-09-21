"""Runtime PID/port state used by ``zett start`` and ``zett stop``."""

import asyncio
import json
import os
import signal
import socket
import subprocess  # noqa: S404
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from ...config import settings
from ...schemas import ProcessRole, ServerRuntimeState
from ..log import get_logger

logger = get_logger(__name__)


class RuntimeStateStore:
    """Atomically manage the JSON runtime-state file below storage_root."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.runtime_state_path
        self._lock = asyncio.Lock()

    async def write(self, state: ServerRuntimeState) -> None:
        async with self._lock:
            await asyncio.to_thread(self._write_unlocked, state)

    async def read(self) -> ServerRuntimeState | None:
        async with self._lock:
            return await asyncio.to_thread(self._read_unlocked)

    async def update_children(self, *, scheduler_pids: list[int], worker_pids: list[int]) -> None:
        """Refresh only scheduler/worker PIDs while preserving server identity."""
        async with self._lock:
            current = await asyncio.to_thread(self._read_unlocked)
            if current is None:
                return
            updated = current.model_copy(
                update={
                    "scheduler_pids": sorted(set(scheduler_pids)),
                    "worker_pids": sorted(set(worker_pids)),
                }
            )
            await asyncio.to_thread(self._write_unlocked, updated)

    async def remove(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self.path.unlink, missing_ok=True)

    def _read_unlocked(self) -> ServerRuntimeState | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except OSError, json.JSONDecodeError:
            logger.exception("Could not read runtime state; path=%s", self.path)
            return None
        try:
            return ServerRuntimeState.model_validate(payload)
        except ValueError:
            logger.exception("Runtime state has an invalid shape; path=%s", self.path)
            return None

    def _write_unlocked(self, state: ServerRuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        finally:
            temporary_path.unlink(missing_ok=True)


class RuntimeProcessController:
    """Coordinate startup safety and stop the server plus owned child processes."""

    def __init__(self, store: RuntimeStateStore | None = None) -> None:
        self.store = store or RuntimeStateStore()

    async def prepare_start(self, *, port: int) -> ServerRuntimeState:
        """Reject a live server/port and clean stale state before a new server starts."""
        state = await self.store.read()
        if state is not None:
            if state.server_pid is not None and self._pid_running(state.server_pid):
                raise RuntimeError(f"Zett is already running with PID {state.server_pid}")
            if state.server_pid is None and state.port is not None and self._port_open(state.port):
                raise RuntimeError(f"Port {state.port} is already in use, but no server PID is recorded")
            await self._terminate_children(state)
            await self.store.remove()
        if self._port_open(port):
            raise RuntimeError(f"Port {port} is already in use")
        return ServerRuntimeState(server_pid=None, port=port, started_at=datetime.now(UTC))

    async def stop(self, *, timeout: float = 10.0) -> ServerRuntimeState | None:
        """Stop the recorded server and child PIDs, then remove the state file."""
        state = await self.store.read()
        if state is None:
            if self.store.path.exists():
                await self.store.remove()
            return None
        if state.server_pid is not None and self._pid_running(state.server_pid):
            await self._terminate_pid(state.server_pid, timeout=timeout, allow_any=True)
        elif state.server_pid is None and state.port is not None:
            port_pids = self._port_pids(state.port)
            if not port_pids:
                logger.error("No PID could be resolved for recorded port %d", state.port)
            for pid in port_pids:
                await self._terminate_pid(pid, timeout=timeout, allow_any=True)
        await self._terminate_children(state, timeout=timeout)
        await self.store.remove()
        return state

    async def _terminate_children(self, state: ServerRuntimeState, *, timeout: float = 5.0) -> None:
        for pid in (*state.scheduler_pids, *state.worker_pids):
            await self._terminate_pid(pid, timeout=timeout, expected="zett")

    async def _terminate_pid(
        self,
        pid: int,
        *,
        timeout: float,
        expected: str | None = None,
        allow_any: bool = False,
    ) -> None:
        if not self._pid_running(pid):
            return
        if not allow_any:
            command = self._command_line(pid)
            if expected is not None and command is not None and expected not in command:
                logger.warning("Skip stopping PID %d because command does not match %r: %s", pid, expected, command)
                return
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._pid_running(pid):
                return
            await asyncio.sleep(0.1)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    @staticmethod
    def _pid_running(pid: int) -> bool:
        if pid <= 1:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _command_line(pid: int) -> str | None:
        try:
            result = subprocess.run(  # noqa: S603
                ["ps", "-p", str(pid), "-o", "command="],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except OSError, subprocess.SubprocessError:
            return None
        return result.stdout.strip() or None

    @staticmethod
    def _port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    @staticmethod
    def _port_pids(port: int) -> list[int]:
        try:
            result = subprocess.run(  # noqa: S603
                ["lsof", "-ti", f"tcp:{port}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except OSError, subprocess.SubprocessError:
            return []
        return [int(value) for value in result.stdout.split() if value.isdigit()]


class RuntimeWatchdog:
    """Exit a scheduler/worker when its owning FastAPI process disappears.

    FastAPI can crash without running lifespan cleanup, while scheduler and
    worker subprocesses keep running. The runtime file is therefore treated as
    the parent lease: the child requires a complete file, a live server PID,
    and its own PID in the scheduler/worker list. Repeated validation failures
    mean the process is orphaned, so it exits instead of continuing forever.
    """

    def __init__(
        self,
        *,
        role: ProcessRole,
        pid: int | None = None,
        store: RuntimeStateStore | None = None,
        interval_seconds: float = settings.process_watchdog_interval_seconds,
        failure_threshold: int = settings.process_watchdog_failure_threshold,
        on_orphaned: Callable[[str], Awaitable[None]],
    ) -> None:
        self.role = role
        self.pid = pid or os.getpid()
        self.store = store or RuntimeStateStore()
        self.interval_seconds = max(0.1, interval_seconds)
        self.failure_threshold = max(1, failure_threshold)
        self.on_orphaned = on_orphaned
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the periodic parent-lease validation loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"runtime-watchdog:{self.role.value}")

    async def stop(self) -> None:
        """Stop the watchdog during normal process cleanup."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def check_once(self) -> str | None:
        """Return a terminal reason when this process is no longer owned."""
        state = await self.store.read()
        if state is None:
            return "runtime state file is missing, unreadable, or malformed"
        if state.server_pid is None:
            return "runtime state has no server_pid"
        if state.port is None:
            return "runtime state has no port"
        if not RuntimeProcessController._pid_running(state.server_pid):
            return f"owning FastAPI process {state.server_pid} is not running"
        role_pids = state.scheduler_pids if self.role is ProcessRole.SCHEDULER else state.worker_pids
        if self.pid not in role_pids:
            return f"current {self.role.value} PID {self.pid} is not registered in runtime state"
        return None

    async def _run(self) -> None:
        failures = 0
        while True:
            await asyncio.sleep(self.interval_seconds)
            reason = await self.check_once()
            if reason is None:
                failures = 0
                continue
            failures += 1
            logger.error(
                "Runtime watchdog validation failed; role=%s pid=%d failures=%d/%d reason=%s",
                self.role.value,
                self.pid,
                failures,
                self.failure_threshold,
                reason,
            )
            if failures < self.failure_threshold:
                continue
            logger.error(
                "Runtime watchdog is terminating orphaned process; role=%s pid=%d reason=%s",
                self.role.value,
                self.pid,
                reason,
            )
            await self.on_orphaned(reason)
            return

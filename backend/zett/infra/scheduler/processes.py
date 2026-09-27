"""OS process launchers and heartbeat publishers for scheduler services."""

import asyncio
import os
import subprocess  # noqa: S404
import sys
import time
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ...config import settings
from ...schemas import ProcessHeartbeatIn, ProcessHeartbeatStatus, ProcessRole
from ..log import get_logger
from . import process_platform

logger = get_logger(__name__)

#: Console output of a detached ``zett start`` server. Nothing is attached to
#: that process' stdout, so startup lines and tracebacks have to land in a file.
BACKGROUND_LOG_FILE_NAME = "background.log"


@dataclass(slots=True)
class ManagedProcess:
    """One child process started by the Web supervisor."""

    role: ProcessRole
    instance_id: str
    process: subprocess.Popen[bytes]
    # Monotonic launch time lets the supervisor distinguish a child that is
    # still starting from one that stopped reporting heartbeats later.
    started_at: float = field(default_factory=time.monotonic)

    @property
    def pid(self) -> int:
        return self.process.pid

    def is_running(self) -> bool:
        return self.process.poll() is None


class SubprocessLauncher:
    """Start scheduler and worker CLI processes without blocking the ASGI loop."""

    def start(self, role: ProcessRole, instance_id: str) -> ManagedProcess:
        if role not in {ProcessRole.SCHEDULER, ProcessRole.WORKER}:
            raise ValueError(f"Unsupported supervised process role: {role}")
        command = [
            sys.executable,
            "-m",
            "zett.cli",
            role.value,
            "--instance-id",
            instance_id,
        ]
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **process_platform.spawn_kwargs(),
        )
        return ManagedProcess(role=role, instance_id=instance_id, process=process)


@dataclass(slots=True)
class BackgroundServerProcess:
    """One detached server process started by ``zett start``."""

    pid: int
    log_path: Path

    def is_running(self) -> bool:
        return process_platform.is_process_running(self.pid)


def launch_background_server(
    *,
    host: str,
    port: int,
    reload: bool,
    log_path: Path,
) -> BackgroundServerProcess:
    """Detach one server process and return its PID and console log file.

    The caller returns to the shell as soon as the server answers on its port,
    so the child runs itself in the foreground from a new session and keeps no
    handle on this terminal. Its stdout and stderr go to ``log_path``: startup
    tracebacks are the only record left when a detached process fails before it
    can write runtime state.
    """
    command = [
        sys.executable,
        "-m",
        "zett.cli",
        "start",
        "--foreground",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        command.append("--reload")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as stream, warnings.catch_warnings():
        # This process returns to the shell while the server keeps running, so
        # it deliberately keeps no child handle: liveness is answered by
        # ``is_process_running``. Dropping that handle here — inside the
        # filtering block — keeps the intentional detachment from being
        # reported as an unwaited child process.
        warnings.simplefilter("ignore", ResourceWarning)
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **process_platform.background_spawn_kwargs(),
        )
        pid = process.pid
        del process
    logger.info("Started background Zett server; pid=%d log_file=%s", pid, log_path)
    return BackgroundServerProcess(pid=pid, log_path=log_path)


class HeartbeatReporter(ABC):
    """Send one heartbeat to the FastAPI process."""

    @abstractmethod
    async def report(self, heartbeat: ProcessHeartbeatIn) -> None:
        """Deliver one heartbeat."""


class HttpHeartbeatReporter(HeartbeatReporter):
    """Post heartbeats to the local FastAPI health endpoint."""

    def __init__(self, base_url: str | None = None) -> None:
        host = process_platform.dialable_host(settings.host)
        self.base_url = (base_url or f"http://{host}:{settings.port}").rstrip("/")

    async def report(self, heartbeat: ProcessHeartbeatIn) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{self.base_url}/api/health/processes/heartbeat",
                json=heartbeat.model_dump(mode="json"),
            )
            response.raise_for_status()


class ProcessHeartbeatPublisher:
    """Periodically post one process heartbeat to the FastAPI service."""

    def __init__(
        self,
        *,
        role: ProcessRole,
        instance_id: str,
        reporter: HeartbeatReporter | None = None,
        interval_seconds: float = settings.heartbeat_interval_seconds,
    ) -> None:
        self.role = role
        self.instance_id = instance_id
        self.pid = os.getpid()
        self.reporter = reporter or HttpHeartbeatReporter()
        self.interval_seconds = max(0.1, interval_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._heartbeat_loop(), name=f"heartbeat:{self.role.value}")
        await self._publish(ProcessHeartbeatStatus.STARTING)
        await self._publish(ProcessHeartbeatStatus.RUNNING)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self._publish(ProcessHeartbeatStatus.STOPPED)

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self._publish(ProcessHeartbeatStatus.RUNNING)
            except asyncio.CancelledError:
                raise

    async def _publish(self, status: ProcessHeartbeatStatus) -> None:
        try:
            await self.reporter.report(
                ProcessHeartbeatIn(
                    role=self.role,
                    instance_id=self.instance_id,
                    pid=self.pid,
                    status=status,
                )
            )
        except Exception:
            logger.exception(
                "Process heartbeat publication failed; role=%s instance_id=%s pid=%d status=%s",
                self.role.value,
                self.instance_id,
                self.pid,
                status.value,
            )

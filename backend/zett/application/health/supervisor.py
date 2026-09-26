"""Local subprocess supervision for scheduler and worker services."""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta

from zett_agent import new_uuid7

from ..._compat import UTC
from ...config import settings
from ...infra.log import get_logger
from ...infra.scheduler.processes import ManagedProcess, SubprocessLauncher
from ...infra.scheduler.runtime_state import RuntimeStateStore
from ...schemas import ProcessRole
from .registry import ProcessHeartbeatRegistry, process_heartbeat_registry

logger = get_logger(__name__)


def _normalize(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ProcessLauncher(ABC):
    """Start one supervised child process."""

    @abstractmethod
    def start(self, role: ProcessRole, instance_id: str) -> ManagedProcess:
        """Start a process and return its local handle."""


class ProcessSupervisor:
    """Keep local scheduler and worker child processes running."""

    def __init__(
        self,
        *,
        launcher: ProcessLauncher | None = None,
        registry: ProcessHeartbeatRegistry | None = None,
        required_workers: int = settings.worker_processes,
        poll_seconds: float = settings.supervisor_poll_seconds,
        heartbeat_timeout_seconds: float = settings.heartbeat_timeout_seconds,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        runtime_state_store: RuntimeStateStore | None = None,
    ) -> None:
        self.launcher = launcher or SubprocessLauncher()
        self.registry = registry or process_heartbeat_registry
        self.required_workers = max(1, required_workers)
        self.poll_seconds = max(0.1, poll_seconds)
        self.heartbeat_timeout_seconds = max(0.1, heartbeat_timeout_seconds)
        self.clock = clock
        self.runtime_state_store = runtime_state_store
        self.instance_id = new_uuid7()
        self._task: asyncio.Task[None] | None = None
        self._managed: dict[ProcessRole, dict[str, ManagedProcess]] = {
            ProcessRole.SCHEDULER: {},
            ProcessRole.WORKER: {},
        }

    async def start(self) -> None:
        """Start supervision in the background without blocking FastAPI."""
        if not settings.process_supervisor_enabled:
            logger.info("Process supervisor disabled by configuration")
            return
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="process-supervisor")
            logger.info(
                "Process supervisor started; instance_id=%s workers=%d",
                self.instance_id,
                self.required_workers,
            )

    async def stop(self) -> None:
        """Stop supervision and terminate locally managed children."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        for role in tuple(self._managed):
            for managed in tuple(self._managed[role].values()):
                await self._terminate(managed)
            self._managed[role].clear()
        await self._persist_child_state()
        logger.info("Process supervisor stopped; instance_id=%s", self.instance_id)

    async def run_once(self, now: datetime | None = None) -> None:
        """Reconcile local scheduler and worker child processes."""
        current = _normalize(now or self.clock())
        stale_before = current - timedelta(seconds=self.heartbeat_timeout_seconds)
        await self._reap_children(now=current)
        await self._ensure_role(ProcessRole.SCHEDULER, required=1, stale_before=stale_before)
        await self._ensure_role(
            ProcessRole.WORKER,
            required=self.required_workers,
            stale_before=stale_before,
        )
        await self._persist_child_state()

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Process supervisor scan failed")
            await asyncio.sleep(self.poll_seconds)

    async def _reap_children(self, *, now: datetime) -> None:
        stale_before = now - timedelta(seconds=self.heartbeat_timeout_seconds)
        for role, managed_by_id in self._managed.items():
            for instance_id, managed in tuple(managed_by_id.items()):
                if not managed.is_running():
                    logger.warning(
                        "Supervised process exited; role=%s instance_id=%s pid=%d exit_code=%s",
                        role.value,
                        instance_id,
                        managed.pid,
                        managed.process.returncode,
                    )
                    managed_by_id.pop(instance_id, None)
                    continue
                heartbeat = await self.registry.get(instance_id)
                if heartbeat is None:
                    # A freshly spawned child may still be importing modules or
                    # initializing SQLite before it can publish its first
                    # heartbeat. Treating that startup window as stale causes
                    # an immediate terminate/restart loop, so allow one full
                    # heartbeat timeout before requiring the first report.
                    if time.monotonic() - managed.started_at < self.heartbeat_timeout_seconds:
                        continue
                    logger.error(
                        "Supervised process never reported a heartbeat; terminating; role=%s instance_id=%s pid=%d",
                        role.value,
                        instance_id,
                        managed.pid,
                    )
                    await self._terminate(managed)
                    managed_by_id.pop(instance_id, None)
                    continue
                if heartbeat.heartbeat_at < stale_before:
                    logger.error(
                        "Supervised process heartbeat is stale; terminating; role=%s instance_id=%s pid=%d",
                        role.value,
                        instance_id,
                        managed.pid,
                    )
                    await self._terminate(managed)
                    managed_by_id.pop(instance_id, None)

    async def _ensure_role(
        self,
        role: ProcessRole,
        *,
        required: int,
        stale_before: datetime,
    ) -> None:
        fresh = await self.registry.list_fresh(role=role, stale_before=stale_before)
        effective_ids = {heartbeat.instance_id for heartbeat in fresh}
        effective_ids.update(
            instance_id for instance_id, managed in self._managed[role].items() if managed.is_running()
        )
        missing = max(0, required - len(effective_ids))
        for _ in range(missing):
            instance_id = new_uuid7()
            try:
                managed = self.launcher.start(role, instance_id)
            except Exception:
                logger.exception(
                    "Could not start supervised process; role=%s instance_id=%s",
                    role.value,
                    instance_id,
                )
                continue
            self._managed[role][instance_id] = managed
            logger.info(
                "Started supervised process; role=%s instance_id=%s pid=%d",
                role.value,
                instance_id,
                managed.pid,
            )

    async def _persist_child_state(self) -> None:
        if self.runtime_state_store is None:
            return
        current = _normalize(self.clock())
        stale_before = current - timedelta(seconds=self.heartbeat_timeout_seconds)
        scheduler_heartbeats = await self.registry.list_fresh(
            role=ProcessRole.SCHEDULER,
            stale_before=stale_before,
        )
        worker_heartbeats = await self.registry.list_fresh(
            role=ProcessRole.WORKER,
            stale_before=stale_before,
        )
        scheduler_pids = [
            managed.pid for managed in self._managed[ProcessRole.SCHEDULER].values() if managed.is_running()
        ]
        worker_pids = [managed.pid for managed in self._managed[ProcessRole.WORKER].values() if managed.is_running()]
        scheduler_pids.extend(heartbeat.pid for heartbeat in scheduler_heartbeats)
        worker_pids.extend(heartbeat.pid for heartbeat in worker_heartbeats)
        await self.runtime_state_store.update_children(
            scheduler_pids=scheduler_pids,
            worker_pids=worker_pids,
        )

    async def _terminate(self, managed: ManagedProcess) -> None:
        if not managed.is_running():
            return
        managed.process.terminate()
        killed = False
        try:
            await asyncio.to_thread(managed.process.wait, timeout=5)
        except Exception:
            logger.warning(
                "Supervised process did not stop after terminate; killing; role=%s instance_id=%s pid=%d",
                managed.role.value,
                managed.instance_id,
                managed.pid,
            )
            managed.process.kill()
            await asyncio.to_thread(managed.process.wait)
            killed = True
        logger.info(
            "Stopped supervised process; role=%s instance_id=%s pid=%d killed=%s",
            managed.role.value,
            managed.instance_id,
            managed.pid,
            killed,
        )

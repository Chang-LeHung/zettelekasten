"""Execution workers that claim pending runs and maintain run status."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic

from ...schemas import (
    ScheduledTaskEntity,
    ScheduledTaskRunStatus,
    ScheduledTaskTrigger,
)
from ..log import get_logger
from ..persistence.dao import ScheduledTaskStorage, scheduled_task_storage
from .contracts import (
    ActionExecutionStatus,
    ActionExecutorRegistry,
    ActionResult,
    ExecutionContext,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerTickResult:
    """Counts produced by one execution-worker scan."""

    recovered: int = 0
    started: int = 0
    skipped: int = 0


@dataclass(slots=True)
class WorkerRunner:
    """Claim queued runs and execute registered actions in an independent process."""

    executors: ActionExecutorRegistry = field(default_factory=ActionExecutorRegistry)
    storage: ScheduledTaskStorage = scheduled_task_storage
    poll_interval: float = 1.0
    error_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    batch_size: int = 100
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _running: set[asyncio.Task[None]] = field(default_factory=set, init=False, repr=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")
        if self.error_backoff_seconds <= 0:
            raise ValueError("error_backoff_seconds must be greater than zero")
        if self.max_backoff_seconds < self.error_backoff_seconds:
            raise ValueError("max_backoff_seconds must be at least error_backoff_seconds")

    async def run_once(self, now: datetime | None = None) -> WorkerTickResult:
        """Recover stale executions and start queued runs."""
        current = self._normalize(now or self.clock())
        recovered = await self.storage.recover_expired_leases(current, limit=self.batch_size)
        for run in recovered:
            logger.warning(
                "Recovered interrupted scheduled run; task_id=%s run_id=%s status=%s",
                run.task_id,
                run.id,
                run.status.value,
            )
        started = 0
        skipped = 0

        for run in await self.storage.list_pending_runs(limit=self.batch_size):
            try:
                task = await self.storage.get(run.task_id)
                if task is None:
                    await self.storage.mark_run_skipped(
                        run_id=run.id,
                        completed_at=current,
                        reason="Scheduled task no longer exists",
                    )
                    skipped += 1
                    logger.warning(
                        "Skipped pending run because task no longer exists; task_id=%s run_id=%s",
                        run.task_id,
                        run.id,
                    )
                    continue
                claimed = await self.storage.claim_pending(
                    now=current,
                    run_id=run.id,
                    task_id=task.id,
                    lease_expires_at=current + timedelta(seconds=task.timeout_seconds + 60),
                    started_at=current,
                )
                if claimed:
                    started += 1
                    logger.info(
                        "Worker claimed scheduled run; task_id=%s task_name=%r run_id=%s "
                        "action_kind=%s trigger=%s scheduled_for=%s",
                        task.id,
                        task.name,
                        run.id,
                        task.action.kind,
                        run.trigger_kind.value,
                        run.scheduled_for.isoformat(),
                    )
                    self._start_execution(
                        task,
                        run_id=run.id,
                        scheduled_for=run.scheduled_for,
                        trigger_kind=run.trigger_kind,
                    )
                else:
                    logger.debug(
                        "Pending run was claimed by another worker or is no longer available; task_id=%s run_id=%s",
                        task.id,
                        run.id,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Could not claim pending scheduled run; task_id=%s run_id=%s",
                    run.task_id,
                    run.id,
                )

        logger.debug(
            "Worker scan completed; recovered=%d started=%d skipped=%d",
            len(recovered),
            started,
            skipped,
        )
        return WorkerTickResult(recovered=len(recovered), started=started, skipped=skipped)

    async def run_forever(self) -> None:
        """Run continuously, retrying transient failures with bounded backoff."""
        self._stop_event.clear()
        backoff = self.error_backoff_seconds
        logger.info(
            "Worker loop started; poll_interval=%.2f batch_size=%d error_backoff=%.2f max_backoff=%.2f",
            self.poll_interval,
            self.batch_size,
            self.error_backoff_seconds,
            self.max_backoff_seconds,
        )
        try:
            while not self._stop_event.is_set():
                try:
                    await self.run_once()
                    backoff = self.error_backoff_seconds
                except asyncio.CancelledError:
                    # Cancellation is an intentional shutdown signal. It can
                    # come from Ctrl+C (SIGINT), a SIGTERM handler that maps the
                    # signal to task cancellation, task.cancel(), asyncio.run()
                    # shutdown, tests, or a process supervisor. A plain stop()
                    # request does not raise here; it sets _stop_event and exits
                    # through the loop condition after active work is cancelled.
                    logger.warning("Worker loop cancellation received; shutting down")
                    raise
                except Exception:
                    logger.exception("Worker scan failed; retrying in %.1f seconds", backoff)
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    except TimeoutError:
                        pass
                    backoff = min(self.max_backoff_seconds, max(self.error_backoff_seconds, backoff * 2))
                    continue
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass
        finally:
            await self.stop()
            logger.info("Worker loop stopped")

    async def stop(self) -> None:
        """Cancel active executions and await their terminal persistence."""
        if not self._stop_event.is_set():
            logger.info("Worker stop requested")
        self._stop_event.set()
        running = tuple(self._running)
        if running:
            logger.warning("Cancelling active scheduled runs; count=%d", len(running))
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def wait_idle(self) -> None:
        """Wait for every execution started by this worker."""
        while self._running:
            await asyncio.gather(*tuple(self._running), return_exceptions=True)

    def _start_execution(
        self,
        task: ScheduledTaskEntity,
        *,
        run_id: str,
        scheduled_for: datetime,
        trigger_kind: ScheduledTaskTrigger,
    ) -> None:
        execution = asyncio.create_task(
            self._execute(
                task,
                run_id=run_id,
                scheduled_for=scheduled_for,
                trigger_kind=trigger_kind,
            ),
            name=f"scheduled-task:{task.id}:{run_id}",
        )
        self._running.add(execution)
        execution.add_done_callback(
            lambda finished: self._execution_finished(
                finished,
                task_id=task.id,
                run_id=run_id,
            )
        )

    def _execution_finished(
        self,
        execution: asyncio.Task[None],
        *,
        task_id: str,
        run_id: str,
    ) -> None:
        """Discard one execution and surface any exception outside _execute."""
        self._running.discard(execution)
        if execution.cancelled():
            logger.warning("Scheduled run execution cancelled; task_id=%s run_id=%s", task_id, run_id)
            return
        error = execution.exception()
        if error is not None:
            logger.error(
                "Unhandled scheduled run execution failure; task_id=%s run_id=%s error_type=%s",
                task_id,
                run_id,
                type(error).__name__,
                exc_info=(type(error), error, error.__traceback__),
            )

    async def _execute(
        self,
        task: ScheduledTaskEntity,
        *,
        run_id: str,
        scheduled_for: datetime,
        trigger_kind: ScheduledTaskTrigger,
    ) -> None:
        context = ExecutionContext(
            task_id=task.id,
            task_name=task.name,
            run_id=run_id,
            scheduled_for=scheduled_for,
            trigger_kind=trigger_kind,
        )
        started_at = monotonic()
        try:
            executor = self.executors.get(task.action.kind)
            if executor is None:
                logger.error(
                    "Scheduled run has no registered executor; task_id=%s run_id=%s action_kind=%s",
                    task.id,
                    run_id,
                    task.action.kind,
                )
                raise LookupError(f"No action executor registered for {task.action.kind!r}")
            payload = executor.validate_payload(task.action.payload)
            async with asyncio.timeout(task.timeout_seconds):
                result: ActionResult = await executor.execute(context, payload)
            status = (
                ScheduledTaskRunStatus.SUCCEEDED
                if result.status is ActionExecutionStatus.SUCCEEDED
                else ScheduledTaskRunStatus.SKIPPED
            )
            await self._finish_run(
                task=task,
                run_id=run_id,
                status=status,
                output=result.output,
            )
            duration_ms = (monotonic() - started_at) * 1_000
            if status is ScheduledTaskRunStatus.SUCCEEDED:
                logger.info(
                    "Scheduled run succeeded; task_id=%s run_id=%s action_kind=%s duration_ms=%.1f",
                    task.id,
                    run_id,
                    task.action.kind,
                    duration_ms,
                )
            else:
                logger.warning(
                    "Scheduled run skipped by executor; task_id=%s run_id=%s action_kind=%s duration_ms=%.1f",
                    task.id,
                    run_id,
                    task.action.kind,
                    duration_ms,
                )
        except TimeoutError as error:
            logger.error(
                "Scheduled run timed out; task_id=%s run_id=%s action_kind=%s timeout_seconds=%d",
                task.id,
                run_id,
                task.action.kind,
                task.timeout_seconds,
                exc_info=(type(error), error, error.__traceback__),
            )
            await self._finish_run(
                task=task,
                run_id=run_id,
                status=ScheduledTaskRunStatus.FAILED,
                error_type=type(error).__name__,
                error_message=str(error),
            )
        except asyncio.CancelledError:
            logger.warning(
                "Scheduled run cancelled; task_id=%s run_id=%s action_kind=%s",
                task.id,
                run_id,
                task.action.kind,
            )
            await self._finish_run(
                task=task,
                run_id=run_id,
                status=ScheduledTaskRunStatus.CANCELLED,
                error_type="CancelledError",
                error_message="Worker process stopped before the run completed",
            )
            raise
        except Exception as error:
            logger.exception(
                "Scheduled run failed; task_id=%s task_name=%r run_id=%s action_kind=%s trigger=%s",
                task.id,
                task.name,
                run_id,
                task.action.kind,
                trigger_kind.value,
            )
            await self._finish_run(
                task=task,
                run_id=run_id,
                status=ScheduledTaskRunStatus.FAILED,
                error_type=type(error).__name__,
                error_message=str(error),
            )

    async def _finish_run(
        self,
        *,
        task: ScheduledTaskEntity,
        run_id: str,
        status: ScheduledTaskRunStatus,
        output: dict[str, object] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Persist a terminal state without hiding the original exception."""
        try:
            await self.storage.finish_run(
                run_id=run_id,
                task_id=task.id,
                status=status,
                completed_at=self._normalize(self.clock()),
                output=output,
                error_type=error_type,
                error_message=error_message,
            )
        except Exception:
            logger.exception(
                "Could not persist scheduled run terminal state; task_id=%s run_id=%s status=%s action_kind=%s",
                task.id,
                run_id,
                status.value,
                task.action.kind,
            )

    @staticmethod
    def _normalize(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

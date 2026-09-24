"""Scheduling control plane that converts due tasks into pending runs."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from zett_agent import new_uuid7

from ..._compat import UTC, TypeAliasType
from ...schemas import (
    CronSchedule,
    ScheduledTaskEntity,
    ScheduledTaskRunCreate,
    ScheduledTaskRunStatus,
    ScheduledTaskTrigger,
)
from ..log import get_logger
from ..persistence.dao import ScheduledTaskStorage, scheduled_task_storage
from .schedule import next_run_after

logger = get_logger(__name__)

NextOccurrence = TypeAliasType("NextOccurrence", Callable[[CronSchedule, datetime], datetime])

#: A queued scheduled run owns its task lease for the execution timeout plus
#: this startup window. The worker extends the same lease when it begins.
QUEUE_START_GRACE_SECONDS = 300


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    """Counts produced by one scheduler control-plane scan."""

    recovered: int = 0
    queued: int = 0
    skipped: int = 0


@dataclass(slots=True)
class SchedulerRunner:
    """Turn due Cron occurrences into durable pending runs.

    This process never executes an action. It only advances ``next_run_at``,
    creates the run row, and assigns the task lease. A separate WorkerRunner
    consumes pending rows, so slow actions cannot delay scheduling.
    """

    next_occurrence: NextOccurrence = next_run_after
    storage: ScheduledTaskStorage = scheduled_task_storage
    poll_interval: float = 1.0
    error_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    batch_size: int = 100
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")
        if self.error_backoff_seconds <= 0:
            raise ValueError("error_backoff_seconds must be greater than zero")
        if self.max_backoff_seconds < self.error_backoff_seconds:
            raise ValueError("max_backoff_seconds must be at least error_backoff_seconds")

    async def run_once(self, now: datetime | None = None) -> SchedulerTickResult:
        """Recover stale leases, claim due occurrences, and queue their runs."""
        current = self._normalize(now or self.clock())
        recovered = await self.storage.recover_expired_leases(current, limit=self.batch_size)
        for run in recovered:
            logger.warning(
                "Recovered interrupted scheduled run; task_id=%s run_id=%s status=%s",
                run.task_id,
                run.id,
                run.status.value,
            )
        queued = 0
        skipped = 0

        for task in await self.storage.list_due_tasks(current, limit=self.batch_size):
            try:
                due_at = self._normalize(task.next_run_at)
                next_run_at = self.next_occurrence(task.schedule, current)
                run = self._scheduled_run(task, due_at)

                # TODO: Replace the one-shot lease with an explicit periodic heartbeat.
                # Current lease lifecycle:
                # 1. Scheduler claim_scheduled() writes lease_run_id/lease_expires_at
                #    when it queues a pending run.
                # 2. Worker claim_pending() renews the same lease for timeout_seconds
                #    plus its startup grace, then marks the run running.
                # 3. Worker finish_run() clears the lease on success, skip, timeout,
                #    cancellation, or error.
                # 4. recover_expired_leases() clears an abandoned lease and marks its
                #    pending/running run interrupted.
                #
                # lease_active only means both lease columns are populated. It does
                # not mean the lease is unexpired; the next comparison decides that.
                lease_active = task.lease_run_id is not None and task.lease_expires_at is not None
                if lease_active and self._normalize(task.lease_expires_at) > current:
                    skipped_run = run.model_copy(
                        update={
                            "status": ScheduledTaskRunStatus.SKIPPED,
                            "completed_at": current,
                            "error_type": "TaskBusy",
                            "error_message": "Previous scheduled run still owns the task lease",
                        }
                    )
                    if await self.storage.record_skipped_occurrence(
                        now=current,
                        task_id=task.id,
                        expected_next_run_at=due_at,
                        next_run_at=next_run_at,
                        run=skipped_run,
                    ):
                        skipped += 1
                        logger.warning(
                            "Skipped scheduled occurrence because task is busy; "
                            "task_id=%s run_id=%s action_kind=%s scheduled_for=%s lease_run_id=%s",
                            task.id,
                            skipped_run.id,
                            task.action.kind,
                            due_at.isoformat(),
                            task.lease_run_id,
                        )
                    continue

                claimed = await self.storage.claim_scheduled(
                    now=current,
                    task_id=task.id,
                    expected_next_run_at=due_at,
                    next_run_at=next_run_at,
                    run=run,
                    lease_expires_at=current + timedelta(seconds=task.timeout_seconds + QUEUE_START_GRACE_SECONDS),
                )
                if claimed:
                    queued += 1
                    logger.info(
                        "Queued scheduled task; task_id=%s task_name=%r run_id=%s "
                        "action_kind=%s scheduled_for=%s next_run_at=%s",
                        task.id,
                        task.name,
                        run.id,
                        task.action.kind,
                        due_at.isoformat(),
                        next_run_at.isoformat(),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Could not schedule due task; task_id=%s task_name=%r action_kind=%s next_run_at=%s",
                    task.id,
                    task.name,
                    task.action.kind,
                    task.next_run_at.isoformat(),
                )

        logger.debug(
            "Scheduler scan completed; recovered=%d queued=%d skipped=%d",
            len(recovered),
            queued,
            skipped,
        )
        return SchedulerTickResult(recovered=len(recovered), queued=queued, skipped=skipped)

    async def run_forever(self) -> None:
        """Run continuously, retrying transient failures with bounded backoff."""
        self._stop_event.clear()
        backoff = self.error_backoff_seconds
        logger.info(
            "Scheduler loop started; poll_interval=%.2f batch_size=%d error_backoff=%.2f max_backoff=%.2f",
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
                    # through the loop condition.
                    logger.warning("Scheduler loop cancellation received; shutting down")
                    raise
                except Exception:
                    logger.exception("Scheduler scan failed; retrying in %.1f seconds", backoff)
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    backoff = min(self.max_backoff_seconds, max(self.error_backoff_seconds, backoff * 2))
                    continue
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.stop()
            logger.info("Scheduler loop stopped")

    def stop(self) -> None:
        """Request a clean stop after the current scheduling scan."""
        if not self._stop_event.is_set():
            logger.info("Scheduler stop requested")
        self._stop_event.set()

    def _scheduled_run(self, task: ScheduledTaskEntity, due_at: datetime) -> ScheduledTaskRunCreate:
        run_id = new_uuid7()
        return ScheduledTaskRunCreate(
            id=run_id,
            task_id=task.id,
            scheduled_for=due_at,
            trigger_kind=ScheduledTaskTrigger.SCHEDULED,
            status=ScheduledTaskRunStatus.PENDING,
            idempotency_key=f"scheduled:{task.id}:{due_at.isoformat()}",
            action=task.action,
        )

    @staticmethod
    def _normalize(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

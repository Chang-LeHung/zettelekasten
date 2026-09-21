"""Framework-neutral use cases for durable scheduled task definitions."""

from collections.abc import Callable
from datetime import UTC, datetime

from zett_agent import new_uuid7

from ...infra.dao import ScheduledTaskStorage, scheduled_task_storage
from ...infra.scheduler import next_run_after
from ...schemas import (
    ScheduledTaskCreate,
    ScheduledTaskEntity,
    ScheduledTaskListOptions,
    ScheduledTaskRunCreate,
    ScheduledTaskRunEntity,
    ScheduledTaskRunListOptions,
    ScheduledTaskRunStatus,
    ScheduledTaskTrigger,
    ScheduledTaskWrite,
)


class ScheduledTaskService:
    """Create, edit, disable, and manually request persisted scheduled tasks."""

    def __init__(
        self,
        storage: ScheduledTaskStorage = scheduled_task_storage,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._storage = storage
        self._clock = clock

    async def create(self, entity: ScheduledTaskCreate) -> ScheduledTaskEntity:
        now = self._now()
        return await self._storage.create(
            ScheduledTaskWrite(
                name=entity.name,
                enabled=entity.enabled,
                schedule=entity.schedule,
                action=entity.action,
                next_run_at=next_run_after(entity.schedule, now),
                timeout_seconds=entity.timeout_seconds,
                overlap_policy=entity.overlap_policy,
            )
        )

    async def get(self, task_id: str) -> ScheduledTaskEntity | None:
        return await self._storage.get(task_id)

    async def list(self, options: ScheduledTaskListOptions | None = None) -> list[ScheduledTaskEntity]:
        return await self._storage.list(options)

    async def update(self, task_id: str, entity: ScheduledTaskCreate) -> ScheduledTaskEntity:
        return await self._storage.update(
            task_id,
            ScheduledTaskWrite(
                name=entity.name,
                enabled=entity.enabled,
                schedule=entity.schedule,
                action=entity.action,
                next_run_at=next_run_after(entity.schedule, self._now()),
                timeout_seconds=entity.timeout_seconds,
                overlap_policy=entity.overlap_policy,
            ),
        )

    async def set_enabled(self, task_id: str, enabled: bool) -> ScheduledTaskEntity:
        task = await self._require(task_id)
        return await self._storage.update(
            task_id,
            ScheduledTaskWrite(
                name=task.name,
                enabled=enabled,
                schedule=task.schedule,
                action=task.action,
                next_run_at=next_run_after(task.schedule, self._now()) if enabled else task.next_run_at,
                timeout_seconds=task.timeout_seconds,
                overlap_policy=task.overlap_policy,
            ),
        )

    async def delete(self, task_id: str) -> bool:
        return await self._storage.delete(task_id)

    async def run_now(self, task_id: str) -> ScheduledTaskRunEntity:
        task = await self._require(task_id)
        now = self._now()
        run_id = new_uuid7()
        return await self._storage.create_run(
            ScheduledTaskRunCreate(
                id=run_id,
                task_id=task.id,
                scheduled_for=now,
                trigger_kind=ScheduledTaskTrigger.MANUAL,
                status=ScheduledTaskRunStatus.PENDING,
                idempotency_key=f"manual:{run_id}",
                action=task.action,
            )
        )

    async def list_runs(
        self,
        options: ScheduledTaskRunListOptions | None = None,
    ) -> list[ScheduledTaskRunEntity]:
        return await self._storage.list_runs(options)

    async def _require(self, task_id: str) -> ScheduledTaskEntity:
        task = await self._storage.get(task_id)
        if task is None:
            raise KeyError(f"Scheduled task not found: {task_id}")
        return task

    def _now(self) -> datetime:
        value = self._clock()
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


scheduled_task_service = ScheduledTaskService()

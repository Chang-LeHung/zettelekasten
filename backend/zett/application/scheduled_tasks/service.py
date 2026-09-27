"""Framework-neutral use cases for durable scheduled task definitions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from zett_agent.ids import new_uuid7

from ..._compat import UTC
from ...infra.persistence.dao import ProviderStorage, ScheduledTaskStorage, provider_storage, scheduled_task_storage
from ...infra.scheduler import next_run_after
from ...schemas import (
    AGENT_PROMPT_ACTION_KIND,
    AgentPromptAction,
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
        provider_validation_storage: ProviderStorage = provider_storage,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._storage = storage
        self._provider_validation_storage = provider_validation_storage
        self._clock = clock

    async def create(self, entity: ScheduledTaskCreate) -> ScheduledTaskEntity:
        await self._validate_provider(entity)
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
        await self._validate_provider(entity)
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
        await self._validate_provider(
            ScheduledTaskCreate(
                name=task.name,
                schedule=task.schedule,
                action=task.action,
                enabled=task.enabled,
                timeout_seconds=task.timeout_seconds,
                overlap_policy=task.overlap_policy,
            )
        )
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

    async def provider_referenced(self, provider_id: str) -> bool:
        """Return whether any scheduled Agent prompt still uses the provider."""
        tasks = await self._storage.list(ScheduledTaskListOptions(limit=500))
        for task in tasks:
            if task.action.kind != AGENT_PROMPT_ACTION_KIND:
                continue
            prompt = AgentPromptAction.model_validate(task.action.payload)
            if prompt.provider_id == provider_id:
                return True
        return False

    async def _require(self, task_id: str) -> ScheduledTaskEntity:
        task = await self._storage.get(task_id)
        if task is None:
            raise KeyError(f"Scheduled task not found: {task_id}")
        return task

    def _now(self) -> datetime:
        value = self._clock()
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    async def _validate_provider(self, entity: ScheduledTaskCreate) -> None:
        """Require the action's provider to exist and be enabled before persistence."""
        if entity.action.kind != AGENT_PROMPT_ACTION_KIND:
            return
        prompt = AgentPromptAction.model_validate(entity.action.payload)
        if await self._provider_validation_storage.resolve_connection(prompt.provider_id) is None:
            raise ValueError("Enabled provider not found")


scheduled_task_service = ScheduledTaskService()

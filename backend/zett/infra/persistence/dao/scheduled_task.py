"""SQLAlchemy persistence and atomic claims for background scheduled tasks."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from zett_agent import new_uuid7

from ...._compat import UTC
from ....schemas import (
    ScheduledTaskAction,
    ScheduledTaskEntity,
    ScheduledTaskListOptions,
    ScheduledTaskOverlapPolicy,
    ScheduledTaskRunCreate,
    ScheduledTaskRunEntity,
    ScheduledTaskRunListOptions,
    ScheduledTaskRunStatus,
    ScheduledTaskTrigger,
    ScheduledTaskWrite,
)
from ..database import session_scope
from ..storage import AsyncStorage
from ..tables import ScheduledTaskRow, ScheduledTaskRunRow


class _RunClaimLost(RuntimeError):
    """Raised internally when another worker claimed the pending run first."""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _action(kind: str, payload: str) -> ScheduledTaskAction:
    return ScheduledTaskAction(kind=kind, payload=json.loads(payload))


def _task_out(model: ScheduledTaskRow) -> ScheduledTaskEntity:
    return ScheduledTaskEntity(
        id=model.id,
        name=model.name,
        enabled=model.enabled,
        schedule=json.loads(model.schedule_json),
        action=_action(model.action_kind, model.action_payload_json),
        next_run_at=_as_utc(model.next_run_at),
        timeout_seconds=model.timeout_seconds,
        overlap_policy=ScheduledTaskOverlapPolicy(model.overlap_policy),
        lease_run_id=model.lease_run_id,
        lease_expires_at=_as_utc(model.lease_expires_at),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _run_out(model: ScheduledTaskRunRow) -> ScheduledTaskRunEntity:
    return ScheduledTaskRunEntity(
        id=model.id,
        task_id=model.task_id,
        scheduled_for=_as_utc(model.scheduled_for),
        trigger_kind=ScheduledTaskTrigger(model.trigger_kind),
        status=ScheduledTaskRunStatus(model.status),
        idempotency_key=model.idempotency_key,
        action=_action(model.action_kind, model.action_payload_json),
        started_at=_as_utc(model.started_at),
        completed_at=_as_utc(model.completed_at),
        output=json.loads(model.output_json) if model.output_json is not None else None,
        error_type=model.error_type,
        error_message=model.error_message,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _task_values(entity: ScheduledTaskWrite, *, now: datetime) -> dict[str, object]:
    return {
        "name": entity.name,
        "enabled": entity.enabled,
        "schedule_json": _encode(entity.schedule.model_dump(mode="json")),
        "action_kind": entity.action.kind,
        "action_payload_json": _encode(entity.action.payload),
        "next_run_at": entity.next_run_at,
        "timeout_seconds": entity.timeout_seconds,
        "overlap_policy": entity.overlap_policy.value,
        "updated_at": now,
    }


class ScheduledTaskStorage(AsyncStorage[ScheduledTaskWrite, ScheduledTaskEntity, str, ScheduledTaskListOptions]):
    """Persist task definitions and claim due work through conditional updates."""

    async def create(self, entity: ScheduledTaskWrite) -> ScheduledTaskEntity:
        now = datetime.now(UTC)
        async with session_scope() as session:
            model = ScheduledTaskRow(
                id=new_uuid7(),
                **_task_values(entity, now=now),
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _task_out(model)

    async def get(self, entity_id: str) -> ScheduledTaskEntity | None:
        async with session_scope() as session:
            model = await session.get(ScheduledTaskRow, entity_id)
            return _task_out(model) if model is not None else None

    async def update(self, entity_id: str, entity: ScheduledTaskWrite) -> ScheduledTaskEntity:
        async with session_scope() as session:
            model = await session.get(ScheduledTaskRow, entity_id)
            if model is None:
                raise KeyError(f"Scheduled task not found: {entity_id}")
            for key, value in _task_values(entity, now=datetime.now(UTC)).items():
                setattr(model, key, value)
            await session.flush()
            return _task_out(model)

    async def delete(self, entity_id: str) -> bool:
        async with session_scope() as session:
            model = await session.get(ScheduledTaskRow, entity_id)
            if model is None:
                return False
            now = datetime.now(UTC)
            if model.lease_run_id is not None and model.lease_expires_at is not None:
                if _as_utc(model.lease_expires_at) > now:
                    raise ValueError("Scheduled task has an active run")
            await session.execute(sql_delete(ScheduledTaskRunRow).where(ScheduledTaskRunRow.task_id == entity_id))
            await session.delete(model)
            return True

    async def list(self, options: ScheduledTaskListOptions | None = None) -> list[ScheduledTaskEntity]:
        options = options or ScheduledTaskListOptions()
        async with session_scope() as session:
            statement = select(ScheduledTaskRow)
            if options.enabled is not None:
                statement = statement.where(ScheduledTaskRow.enabled.is_(options.enabled))
            statement = (
                statement.order_by(ScheduledTaskRow.next_run_at, ScheduledTaskRow.id)
                .limit(options.limit)
                .offset(options.offset)
            )
            return [_task_out(model) for model in await session.scalars(statement)]

    async def list_due_tasks(self, now: datetime, *, limit: int = 100) -> list[ScheduledTaskEntity]:
        """Return enabled tasks whose persisted occurrence is due."""
        async with session_scope() as session:
            statement = (
                select(ScheduledTaskRow)
                .where(
                    ScheduledTaskRow.enabled.is_(True),
                    ScheduledTaskRow.next_run_at <= now,
                )
                .order_by(ScheduledTaskRow.next_run_at, ScheduledTaskRow.id)
                .limit(limit)
            )
            return [_task_out(model) for model in await session.scalars(statement)]

    async def claim_scheduled(
        self,
        *,
        now: datetime,
        task_id: str,
        expected_next_run_at: datetime,
        next_run_at: datetime,
        run: ScheduledTaskRunCreate,
        lease_expires_at: datetime,
    ) -> bool:
        """Advance one due occurrence and own it with a new task lease."""
        try:
            async with session_scope() as session:
                result = await session.execute(
                    update(ScheduledTaskRow)
                    .where(
                        ScheduledTaskRow.id == task_id,
                        ScheduledTaskRow.enabled.is_(True),
                        ScheduledTaskRow.next_run_at == expected_next_run_at,
                        or_(
                            ScheduledTaskRow.lease_expires_at.is_(None),
                            ScheduledTaskRow.lease_expires_at <= now,
                        ),
                    )
                    .values(
                        next_run_at=next_run_at,
                        lease_run_id=run.id,
                        lease_expires_at=lease_expires_at,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    return False
                session.add(self._run_row(run, created_at=now))
                await session.flush()
                return True
        except IntegrityError:
            return False

    async def record_skipped_occurrence(
        self,
        *,
        now: datetime,
        task_id: str,
        expected_next_run_at: datetime,
        next_run_at: datetime,
        run: ScheduledTaskRunCreate,
    ) -> bool:
        """Advance one occurrence that was skipped because the task was busy."""
        try:
            async with session_scope() as session:
                result = await session.execute(
                    update(ScheduledTaskRow)
                    .where(
                        ScheduledTaskRow.id == task_id,
                        ScheduledTaskRow.enabled.is_(True),
                        ScheduledTaskRow.next_run_at == expected_next_run_at,
                        ScheduledTaskRow.lease_run_id.is_not(None),
                        ScheduledTaskRow.lease_expires_at > now,
                    )
                    .values(next_run_at=next_run_at, updated_at=now)
                )
                if result.rowcount != 1:
                    return False
                session.add(self._run_row(run, created_at=now))
                await session.flush()
                return True
        except IntegrityError:
            return False

    async def create_run(self, run: ScheduledTaskRunCreate) -> ScheduledTaskRunEntity:
        now = datetime.now(UTC)
        async with session_scope() as session:
            model = self._run_row(run, created_at=now)
            session.add(model)
            await session.flush()
            return _run_out(model)

    async def get_run(self, run_id: str) -> ScheduledTaskRunEntity | None:
        async with session_scope() as session:
            model = await session.get(ScheduledTaskRunRow, run_id)
            return _run_out(model) if model is not None else None

    async def list_runs(
        self,
        options: ScheduledTaskRunListOptions | None = None,
    ) -> list[ScheduledTaskRunEntity]:
        options = options or ScheduledTaskRunListOptions()
        async with session_scope() as session:
            statement = select(ScheduledTaskRunRow)
            if options.task_id is not None:
                statement = statement.where(ScheduledTaskRunRow.task_id == options.task_id)
            if options.statuses:
                statement = statement.where(
                    ScheduledTaskRunRow.status.in_(tuple(status.value for status in options.statuses))
                )
            statement = (
                statement.order_by(ScheduledTaskRunRow.created_at.desc(), ScheduledTaskRunRow.id.desc())
                .limit(options.limit)
                .offset(options.offset)
            )
            return [_run_out(model) for model in await session.scalars(statement)]

    async def list_pending_runs(self, *, limit: int = 100) -> list[ScheduledTaskRunEntity]:
        """Return scheduled and manual runs waiting for an execution worker."""
        async with session_scope() as session:
            statement = (
                select(ScheduledTaskRunRow)
                .where(ScheduledTaskRunRow.status == ScheduledTaskRunStatus.PENDING.value)
                .order_by(ScheduledTaskRunRow.created_at, ScheduledTaskRunRow.id)
                .limit(limit)
            )
            return [_run_out(model) for model in await session.scalars(statement)]

    async def claim_pending(
        self,
        *,
        now: datetime,
        run_id: str,
        task_id: str,
        lease_expires_at: datetime,
        started_at: datetime,
    ) -> bool:
        """Claim one queued run and mark it running under the task lease."""
        try:
            async with session_scope() as session:
                task_result = await session.execute(
                    update(ScheduledTaskRow)
                    .where(
                        ScheduledTaskRow.id == task_id,
                        or_(
                            ScheduledTaskRow.lease_expires_at.is_(None),
                            ScheduledTaskRow.lease_expires_at <= now,
                            ScheduledTaskRow.lease_run_id == run_id,
                        ),
                    )
                    .values(lease_run_id=run_id, lease_expires_at=lease_expires_at, updated_at=now)
                )
                if task_result.rowcount != 1:
                    return False
                run_result = await session.execute(
                    update(ScheduledTaskRunRow)
                    .where(
                        ScheduledTaskRunRow.id == run_id,
                        ScheduledTaskRunRow.status == ScheduledTaskRunStatus.PENDING.value,
                    )
                    .values(
                        status=ScheduledTaskRunStatus.RUNNING.value,
                        started_at=started_at,
                        updated_at=now,
                    )
                )
                if run_result.rowcount != 1:
                    raise _RunClaimLost
                return True
        except _RunClaimLost:
            return False

    async def finish_run(
        self,
        *,
        run_id: str,
        task_id: str,
        status: ScheduledTaskRunStatus,
        completed_at: datetime,
        output: dict[str, object] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> ScheduledTaskRunEntity:
        """Write a terminal run result and release only this run's task lease."""
        async with session_scope() as session:
            model = await session.get(ScheduledTaskRunRow, run_id)
            if model is None:
                raise KeyError(f"Scheduled task run not found: {run_id}")
            model.status = status.value
            model.completed_at = completed_at
            model.output_json = _encode(output) if output is not None else None
            model.error_type = error_type
            model.error_message = error_message
            model.updated_at = completed_at
            await session.execute(
                update(ScheduledTaskRow)
                .where(
                    ScheduledTaskRow.id == task_id,
                    ScheduledTaskRow.lease_run_id == run_id,
                )
                .values(lease_run_id=None, lease_expires_at=None, updated_at=completed_at)
            )
            await session.flush()
            return _run_out(model)

    async def mark_run_skipped(
        self,
        *,
        run_id: str,
        completed_at: datetime,
        reason: str,
    ) -> ScheduledTaskRunEntity:
        """Turn a pending run into a visible skipped result."""
        async with session_scope() as session:
            model = await session.get(ScheduledTaskRunRow, run_id)
            if model is None:
                raise KeyError(f"Scheduled task run not found: {run_id}")
            model.status = ScheduledTaskRunStatus.SKIPPED.value
            model.completed_at = completed_at
            model.error_type = "TaskBusy"
            model.error_message = reason
            model.updated_at = completed_at
            await session.flush()
            return _run_out(model)

    async def recover_expired_leases(self, now: datetime, *, limit: int = 100) -> list[ScheduledTaskRunEntity]:
        """Mark runs whose owning process stopped updating its lease."""
        async with session_scope() as session:
            tasks = list(
                await session.scalars(
                    select(ScheduledTaskRow)
                    .where(
                        ScheduledTaskRow.lease_run_id.is_not(None),
                        ScheduledTaskRow.lease_expires_at <= now,
                    )
                    .order_by(ScheduledTaskRow.lease_expires_at)
                    .limit(limit)
                )
            )
            recovered: list[ScheduledTaskRunEntity] = []
            for task in tasks:
                run_id = task.lease_run_id
                task.lease_run_id = None
                task.lease_expires_at = None
                task.updated_at = now
                if run_id is None:
                    continue
                run = await session.get(ScheduledTaskRunRow, run_id)
                if run is None or run.status not in {
                    ScheduledTaskRunStatus.PENDING.value,
                    ScheduledTaskRunStatus.RUNNING.value,
                }:
                    continue
                run.status = ScheduledTaskRunStatus.INTERRUPTED.value
                run.completed_at = now
                run.error_type = "LeaseExpired"
                run.error_message = "Scheduler or worker process stopped before the run completed"
                run.updated_at = now
                recovered.append(_run_out(run))
            return recovered

    @staticmethod
    def _run_row(entity: ScheduledTaskRunCreate, *, created_at: datetime) -> ScheduledTaskRunRow:
        return ScheduledTaskRunRow(
            id=entity.id,
            task_id=entity.task_id,
            scheduled_for=entity.scheduled_for,
            trigger_kind=entity.trigger_kind.value,
            status=entity.status.value,
            idempotency_key=entity.idempotency_key,
            action_kind=entity.action.kind,
            action_payload_json=_encode(entity.action.payload),
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            output_json=_encode(entity.output) if entity.output is not None else None,
            error_type=entity.error_type,
            error_message=entity.error_message,
            created_at=created_at,
            updated_at=created_at,
        )


scheduled_task_storage = ScheduledTaskStorage()

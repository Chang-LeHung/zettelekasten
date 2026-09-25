"""Scheduled task persistence, execution, and control-plane behavior."""

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from zett_agent import (
    AssistantMessage,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    UserMessage,
    new_uuid7,
)

from zett._compat import UTC
from zett.application.scheduled_tasks import ScheduledTaskService
from zett.infra.persistence.dao import provider_storage, scheduled_task_storage, session_storage
from zett.infra.persistence.database import session_scope
from zett.infra.persistence.tables import ScheduledTaskRow
from zett.infra.scheduler import (
    ActionExecutionStatus,
    ActionExecutor,
    ActionExecutorRegistry,
    ActionResult,
    ExecutionContext,
    SchedulerRunner,
    WorkerRunner,
    next_run_after,
)
from zett.infra.scheduler import agent_prompt as scheduled_agent_module
from zett.infra.scheduler.agent_prompt import scheduled_agent_executor
from zett.main import app
from zett.schemas import (
    SESSION_TYPE_TO_CODE,
    CronSchedule,
    ProviderType,
    ProviderWrite,
    ScheduledTaskAction,
    ScheduledTaskCreate,
    ScheduledTaskEntity,
    ScheduledTaskRunCreate,
    ScheduledTaskRunListOptions,
    ScheduledTaskRunStatus,
    ScheduledTaskTrigger,
    ScheduledTaskWrite,
    SessionType,
)


def _task_create(
    *,
    action_kind: str = "probe",
    action_payload: dict[str, object] | None = None,
    expression: str = "* * * * *",
) -> ScheduledTaskCreate:
    return ScheduledTaskCreate(
        name="Probe task",
        schedule=CronSchedule(expression=expression, timezone="UTC"),
        action=ScheduledTaskAction(kind=action_kind, payload=action_payload or {}),
    )


async def _due_task(*, now: datetime, action_kind: str = "probe") -> ScheduledTaskEntity:
    return await scheduled_task_storage.create(
        ScheduledTaskWrite(
            name="Due task",
            enabled=True,
            schedule=CronSchedule(expression="* * * * *", timezone="UTC"),
            action=ScheduledTaskAction(kind=action_kind, payload={}),
            next_run_at=now - timedelta(seconds=10),
            timeout_seconds=30,
            overlap_policy="skip",
        )
    )


def test_next_run_after_uses_the_task_timezone() -> None:
    schedule = CronSchedule(expression="0 9 * * *", timezone="Asia/Shanghai")

    result = next_run_after(schedule, datetime(2026, 1, 1, 0, 59, tzinfo=UTC))

    assert result == datetime(2026, 1, 1, 1, 0, tzinfo=UTC)


def test_cron_schedule_rejects_unknown_iana_timezone() -> None:
    with pytest.raises(ValueError, match="Unknown timezone"):
        CronSchedule(expression="0 9 * * *", timezone="Mars/Olympus")


def test_scheduled_task_indexes_are_independent_columns(isolated_database) -> None:
    expected = {
        "scheduled_tasks": {"next_run_at", "lease_expires_at"},
        "scheduled_task_runs": {"task_id", "status", "idempotency_key"},
    }

    with sqlite3.connect(isolated_database) as connection:
        for table_name, expected_columns in expected.items():
            indexed_columns: set[str] = set()
            for index in connection.execute(f"pragma index_list({table_name})").fetchall():
                index_name = index[1]
                if index_name.startswith("sqlite_"):
                    continue
                columns = connection.execute(f"pragma index_info({index_name})").fetchall()
                assert len(columns) == 1, f"{table_name}.{index_name} should index one column"
                indexed_columns.add(columns[0][2])
            assert indexed_columns == expected_columns


async def test_scheduled_task_storage_claims_one_occurrence_atomically() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    task = await _due_task(now=now)
    run = ScheduledTaskRunCreate(
        id=new_uuid7(),
        task_id=task.id,
        scheduled_for=task.next_run_at,
        trigger_kind=ScheduledTaskTrigger.SCHEDULED,
        status=ScheduledTaskRunStatus.PENDING,
        idempotency_key=f"probe:{task.id}:{task.next_run_at.isoformat()}",
        action=task.action,
    )
    next_run_at = now + timedelta(minutes=1)

    first = await scheduled_task_storage.claim_scheduled(
        now=now,
        task_id=task.id,
        expected_next_run_at=task.next_run_at,
        next_run_at=next_run_at,
        run=run,
        lease_expires_at=now + timedelta(seconds=30),
    )
    second = await scheduled_task_storage.claim_scheduled(
        now=now,
        task_id=task.id,
        expected_next_run_at=task.next_run_at,
        next_run_at=next_run_at,
        run=run,
        lease_expires_at=now + timedelta(seconds=30),
    )

    assert first is True
    assert second is False
    claimed = await scheduled_task_storage.get(task.id)
    assert claimed is not None
    assert claimed.next_run_at == next_run_at
    assert claimed.lease_run_id == run.id
    runs = await scheduled_task_storage.list_runs(ScheduledTaskRunListOptions(task_id=task.id))
    assert [item.status for item in runs] == [ScheduledTaskRunStatus.PENDING]


class RecordingExecutor(ActionExecutor):
    """Return one deterministic result and retain each execution context."""

    action_kind = "probe"

    def __init__(self) -> None:
        self.calls: list[tuple[ExecutionContext, Mapping[str, object]]] = []

    def validate_payload(self, payload: Mapping[str, object]) -> dict[str, object]:
        return dict(payload)

    async def execute(
        self,
        context: ExecutionContext,
        payload: Mapping[str, object],
    ) -> ActionResult:
        self.calls.append((context, payload))
        return ActionResult(
            status=ActionExecutionStatus.SUCCEEDED,
            output={"executed": True},
        )


async def test_scheduler_queues_due_task_and_worker_executes_it() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    task = await _due_task(now=now)
    executor = RecordingExecutor()
    scheduler = SchedulerRunner(
        next_occurrence=next_run_after,
        clock=lambda: now,
    )

    scheduler_result = await scheduler.run_once(now)

    assert scheduler_result.queued == 1
    assert executor.calls == []
    runs = await scheduled_task_storage.list_runs(ScheduledTaskRunListOptions(task_id=task.id))
    assert len(runs) == 1
    assert runs[0].status is ScheduledTaskRunStatus.PENDING
    queued = await scheduled_task_storage.get(task.id)
    assert queued is not None
    assert queued.lease_run_id == runs[0].id
    assert queued.next_run_at > now

    worker = WorkerRunner(
        executors=ActionExecutorRegistry((executor,)),
        clock=lambda: now,
    )
    worker_result = await worker.run_once(now)
    await worker.wait_idle()

    assert worker_result.started == 1
    assert len(executor.calls) == 1
    completed = await scheduled_task_storage.get_run(runs[0].id)
    assert completed is not None
    assert completed.status is ScheduledTaskRunStatus.SUCCEEDED
    assert completed.output == {"executed": True}
    refreshed = await scheduled_task_storage.get(task.id)
    assert refreshed is not None
    assert refreshed.lease_run_id is None
    assert refreshed.lease_expires_at is None


async def test_scheduler_runner_skips_occurrence_while_task_lease_is_active() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    task = await _due_task(now=now)
    running = ScheduledTaskRunCreate(
        id=new_uuid7(),
        task_id=task.id,
        scheduled_for=task.next_run_at,
        trigger_kind=ScheduledTaskTrigger.SCHEDULED,
        status=ScheduledTaskRunStatus.RUNNING,
        idempotency_key=f"running:{task.id}",
        action=task.action,
        started_at=now,
    )
    await scheduled_task_storage.create_run(running)
    async with session_scope() as session:
        await session.execute(
            update(ScheduledTaskRow)
            .where(ScheduledTaskRow.id == task.id)
            .values(
                next_run_at=task.next_run_at,
                lease_run_id=running.id,
                lease_expires_at=now + timedelta(minutes=1),
            )
        )
    runner = SchedulerRunner(
        next_occurrence=next_run_after,
        clock=lambda: now,
    )
    due = await scheduled_task_storage.list_due_tasks(now)
    assert [item.id for item in due] == [task.id]

    result = await runner.run_once(now)

    assert result.skipped == 1
    runs = await scheduled_task_storage.list_runs(ScheduledTaskRunListOptions(task_id=task.id))
    assert {item.status for item in runs} == {
        ScheduledTaskRunStatus.RUNNING,
        ScheduledTaskRunStatus.SKIPPED,
    }


async def test_scheduler_queues_an_occurrence_that_was_discovered_late() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    task = await scheduled_task_storage.create(
        ScheduledTaskWrite(
            name="Late task",
            enabled=True,
            schedule=CronSchedule(expression="* * * * *", timezone="UTC"),
            action=ScheduledTaskAction(kind="probe", payload={}),
            next_run_at=now - timedelta(days=1),
            timeout_seconds=30,
            overlap_policy="skip",
        )
    )
    runner = SchedulerRunner(
        next_occurrence=next_run_after,
        clock=lambda: now,
    )

    result = await runner.run_once(now)

    assert result.queued == 1
    runs = await scheduled_task_storage.list_runs(ScheduledTaskRunListOptions(task_id=task.id))
    assert runs[0].status is ScheduledTaskRunStatus.PENDING


async def test_run_now_is_claimed_by_the_worker() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = ScheduledTaskService(clock=lambda: now)
    task = await service.create(_task_create())
    pending = await service.run_now(task.id)
    executor = RecordingExecutor()
    runner = WorkerRunner(
        executors=ActionExecutorRegistry((executor,)),
        clock=lambda: now,
    )

    result = await runner.run_once(now)
    await runner.wait_idle()

    assert pending.status is ScheduledTaskRunStatus.PENDING
    assert result.started == 1
    run = await scheduled_task_storage.get_run(pending.id)
    assert run is not None and run.status is ScheduledTaskRunStatus.SUCCEEDED
    assert run.trigger_kind is ScheduledTaskTrigger.MANUAL


async def test_pending_run_can_only_be_claimed_by_one_worker() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    task = await _due_task(now=now)
    pending = await scheduled_task_storage.create_run(
        ScheduledTaskRunCreate(
            id=new_uuid7(),
            task_id=task.id,
            scheduled_for=now,
            trigger_kind=ScheduledTaskTrigger.MANUAL,
            status=ScheduledTaskRunStatus.PENDING,
            idempotency_key=f"manual:{new_uuid7()}",
            action=task.action,
        )
    )

    claims = await asyncio.gather(
        scheduled_task_storage.claim_pending(
            now=now,
            run_id=pending.id,
            task_id=task.id,
            lease_expires_at=now + timedelta(minutes=1),
            started_at=now,
        ),
        scheduled_task_storage.claim_pending(
            now=now,
            run_id=pending.id,
            task_id=task.id,
            lease_expires_at=now + timedelta(minutes=1),
            started_at=now,
        ),
    )

    assert sorted(claims) == [False, True]


async def test_scheduler_run_forever_retries_after_a_scan_error(monkeypatch) -> None:
    runner = SchedulerRunner(
        poll_interval=0.01,
        error_backoff_seconds=0.001,
        max_backoff_seconds=0.001,
    )
    calls = 0

    async def flaky_scan(_self, _now=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        runner.stop()
        return None

    monkeypatch.setattr(SchedulerRunner, "run_once", flaky_scan)

    await runner.run_forever()

    assert calls == 2


async def test_worker_run_forever_retries_after_a_scan_error(monkeypatch) -> None:
    runner = WorkerRunner(
        poll_interval=0.01,
        error_backoff_seconds=0.001,
        max_backoff_seconds=0.001,
    )
    calls = 0

    async def flaky_scan(_self, _now=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        await runner.stop()
        return None

    monkeypatch.setattr(WorkerRunner, "run_once", flaky_scan)

    await runner.run_forever()

    assert calls == 2


def test_scheduled_task_http_control_plane() -> None:
    with TestClient(app) as client:
        provider = client.post(
            "/api/ai/providers",
            json={
                "name": "Scheduled provider",
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "https://example.invalid/v1",
                "api_key": "secret",
                "enabled": True,
            },
        )
        assert provider.status_code == 201
        provider_id = provider.json()["id"]
        created = client.post(
            "/api/scheduled-tasks",
            json={
                "name": "Daily note",
                "schedule": {"expression": "0 9 * * *", "timezone": "Asia/Shanghai"},
                "action": {
                    "kind": "agent_prompt",
                    "payload": {
                        "provider_id": provider_id,
                        "message": "Create a daily note.",
                    },
                },
            },
        )
        assert created.status_code == 201
        task = created.json()
        assert client.get("/api/scheduled-tasks").json()[0]["id"] == task["id"]
        assert client.get(f"/api/scheduled-tasks/{task['id']}").json()["name"] == "Daily note"
        assert client.delete(f"/api/ai/providers/{provider_id}").status_code == 409

        disabled = client.patch(
            f"/api/scheduled-tasks/{task['id']}/enabled",
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        pending = client.post(f"/api/scheduled-tasks/{task['id']}/run")
        assert pending.status_code == 202
        assert pending.json()["status"] == "pending"
        assert client.get(f"/api/scheduled-tasks/{task['id']}/runs").json()[0]["id"] == pending.json()["id"]

        invalid = client.post(
            "/api/scheduled-tasks",
            json={
                "name": "Invalid",
                "schedule": {"expression": "not cron", "timezone": "UTC"},
                "action": {"kind": "agent_prompt", "payload": {"provider_id": "p", "message": "x"}},
            },
        )
        assert invalid.status_code == 422

        missing_provider = client.post(
            "/api/scheduled-tasks",
            json={
                "name": "Missing provider",
                "schedule": {"expression": "0 9 * * *", "timezone": "UTC"},
                "action": {"kind": "agent_prompt", "payload": {"provider_id": "missing", "message": "x"}},
            },
        )
        assert missing_provider.status_code == 422
        assert "Enabled provider not found" in missing_provider.text

        invalid_effort = client.post(
            "/api/scheduled-tasks",
            json={
                "name": "Invalid effort",
                "schedule": {"expression": "0 9 * * *", "timezone": "UTC"},
                "action": {
                    "kind": "agent_prompt",
                    "payload": {"provider_id": provider_id, "message": "x", "reasoning_effort": "impossible"},
                },
            },
        )
        assert invalid_effort.status_code == 422
        assert client.delete(f"/api/scheduled-tasks/{task['id']}").json() == {"ok": True}


async def test_agent_prompt_executor_creates_a_fresh_noninteractive_session(monkeypatch) -> None:
    class ProbeModel:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            del request
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="scheduled result")))

        async def aclose(self) -> None:
            return None

    original_config = scheduled_agent_module.ZettelkastenAgentConfig
    captured_config: dict[str, object] = {}
    monkeypatch.setattr(scheduled_agent_module, "create_model", lambda _connection: ProbeModel())

    def config_factory(**options: object):
        captured_config.update(options)
        return original_config(**options, skill_roots=(), mcp_config_path=None)

    monkeypatch.setattr(
        scheduled_agent_module,
        "ZettelkastenAgentConfig",
        config_factory,
    )
    provider = await provider_storage.create(
        ProviderWrite(
            name="Scheduled provider",
            provider=ProviderType.OPENAI_COMPATIBLE,
            model="probe-model",
            base_url="https://example.invalid/v1",
            api_key="secret",
        )
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)

    result = await scheduled_agent_executor.execute(
        ExecutionContext(
            task_id="task-id",
            task_name="Scheduled title",
            run_id=new_uuid7(),
            scheduled_for=now,
            trigger_kind=ScheduledTaskTrigger.MANUAL,
        ),
        {"provider_id": provider.id, "message": "Run the scheduled prompt."},
    )

    assert result.status is ActionExecutionStatus.SUCCEEDED
    assert result.output is not None
    assert captured_config["allow_direct_artifact_edits"] is True
    session_id = result.output["session_id"]
    assert isinstance(session_id, str)
    session = await session_storage.get(session_id)
    assert session is not None and session.title == "Scheduled title"
    assert session.session_type == SESSION_TYPE_TO_CODE[SessionType.SCHEDULED]
    records = await session_storage.list_raw_messages(session_id)
    dialogue = [record.message for record in records if isinstance(record.message, UserMessage | AssistantMessage)]
    assert [message.text if isinstance(message, UserMessage) else message.content for message in dialogue] == [
        "Run the scheduled prompt.",
        "scheduled result",
    ]

"""In-memory heartbeat, health, and process-supervision behavior."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from zett.application.health import (
    ProcessHealthService,
    ProcessHeartbeatRegistry,
    ProcessLauncher,
    ProcessSupervisor,
)
from zett.config import settings
from zett.infra.scheduler.processes import HeartbeatReporter, ProcessHeartbeatPublisher
from zett.main import app
from zett.schemas import ProcessHeartbeatIn, ProcessHeartbeatStatus, ProcessRole


async def test_heartbeat_registry_preserves_started_at_and_health() -> None:
    registry = ProcessHeartbeatRegistry()
    first = await registry.record(
        ProcessHeartbeatIn(
            role=ProcessRole.SCHEDULER,
            instance_id="scheduler-1",
            pid=101,
            status=ProcessHeartbeatStatus.STARTING,
        ),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = await registry.record(
        ProcessHeartbeatIn(
            role=ProcessRole.SCHEDULER,
            instance_id="scheduler-1",
            pid=102,
            status=ProcessHeartbeatStatus.RUNNING,
        ),
        now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
    )

    assert second.started_at == first.started_at
    assert second.heartbeat_at == datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
    assert second.pid == 102
    assert [
        item.instance_id
        for item in await registry.list_fresh(
            role=ProcessRole.SCHEDULER,
            stale_before=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ] == ["scheduler-1"]


async def test_process_health_requires_fresh_scheduler_and_workers() -> None:
    registry = ProcessHeartbeatRegistry()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for role, instance_id, pid in (
        (ProcessRole.SCHEDULER, "scheduler-1", 101),
        (ProcessRole.WORKER, "worker-1", 201),
    ):
        await registry.record(
            ProcessHeartbeatIn(
                role=role,
                instance_id=instance_id,
                pid=pid,
                status=ProcessHeartbeatStatus.RUNNING,
            ),
            now=now,
        )
    service = ProcessHealthService(
        registry=registry,
        required_workers=1,
        heartbeat_timeout_seconds=20,
        clock=lambda: now + timedelta(seconds=5),
    )

    report = await service.report()

    assert report.healthy is True
    assert [role.active_processes for role in report.roles] == [1, 1]


async def test_heartbeat_publisher_repeats_on_its_interval() -> None:
    class RecordingReporter(HeartbeatReporter):
        def __init__(self) -> None:
            self.statuses: list[ProcessHeartbeatStatus] = []

        async def report(self, heartbeat: ProcessHeartbeatIn) -> None:
            self.statuses.append(heartbeat.status)

    reporter = RecordingReporter()
    publisher = ProcessHeartbeatPublisher(
        role=ProcessRole.SCHEDULER,
        instance_id="scheduler-heartbeat",
        reporter=reporter,
        interval_seconds=0.1,
    )

    await publisher.start()
    await asyncio.sleep(0.25)
    await publisher.stop()

    assert reporter.statuses[0] is ProcessHeartbeatStatus.STARTING
    assert reporter.statuses.count(ProcessHeartbeatStatus.RUNNING) >= 3


class FakeProcess:
    """Small Popen-compatible process used by supervisor tests."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return self.returncode or 0


class FakeManagedProcess:
    """Local process handle returned by the fake launcher."""

    def __init__(self, role: ProcessRole, instance_id: str, pid: int) -> None:
        self.role = role
        self.instance_id = instance_id
        self.process = FakeProcess(pid)
        self.pid = pid

    def is_running(self) -> bool:
        return self.process.poll() is None


class FakeLauncher(ProcessLauncher):
    """Record process launches without starting real child processes."""

    def __init__(self) -> None:
        self.started: list[tuple[ProcessRole, str]] = []

    def start(self, role: ProcessRole, instance_id: str) -> FakeManagedProcess:
        self.started.append((role, instance_id))
        return FakeManagedProcess(role, instance_id, len(self.started) + 100)


async def test_supervisor_starts_missing_scheduler_and_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "process_supervisor_enabled", True)
    launcher = FakeLauncher()
    registry = ProcessHeartbeatRegistry()
    supervisor = ProcessSupervisor(
        launcher=launcher,
        registry=registry,
        required_workers=1,
        heartbeat_timeout_seconds=20,
    )

    await supervisor.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    await supervisor.stop()

    assert [role for role, _ in launcher.started] == [ProcessRole.SCHEDULER, ProcessRole.WORKER]


async def test_supervisor_does_not_duplicate_fresh_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "process_supervisor_enabled", True)
    registry = ProcessHeartbeatRegistry()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    for role, instance_id, pid in (
        (ProcessRole.SCHEDULER, "scheduler-1", 101),
        (ProcessRole.WORKER, "worker-1", 201),
    ):
        await registry.record(
            ProcessHeartbeatIn(
                role=role,
                instance_id=instance_id,
                pid=pid,
                status=ProcessHeartbeatStatus.RUNNING,
            ),
            now=now,
        )
    launcher = FakeLauncher()
    supervisor = ProcessSupervisor(
        launcher=launcher,
        registry=registry,
        required_workers=1,
        heartbeat_timeout_seconds=20,
    )

    await supervisor.run_once(now)
    await supervisor.stop()

    assert launcher.started == []


def test_process_health_endpoint_receives_in_memory_heartbeats() -> None:
    with TestClient(app) as client:
        for role, instance_id, pid in (
            ("scheduler", "scheduler-1", 101),
            ("worker", "worker-1", 201),
        ):
            heartbeat = client.post(
                "/api/health/processes/heartbeat",
                json={
                    "role": role,
                    "instance_id": instance_id,
                    "pid": pid,
                    "status": "running",
                },
            )
            assert heartbeat.status_code == 202

        response = client.get("/api/health/processes")

    assert response.status_code == 200
    report = response.json()
    assert report["healthy"] is True
    assert [role["role"] for role in report["roles"]] == ["scheduler", "worker"]

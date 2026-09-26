"""In-memory heartbeat, health, and process-supervision behavior."""

import asyncio
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from zett._compat import UTC
from zett.application.health import (
    ProcessHealthService,
    ProcessHeartbeatRegistry,
    ProcessLauncher,
    ProcessSupervisor,
)
from zett.config import settings
from zett.infra.scheduler.processes import HeartbeatReporter, ProcessHeartbeatPublisher
from zett.infra.scheduler.runtime_state import RuntimeStateStore
from zett.main import app
from zett.schemas import ProcessHeartbeatIn, ProcessHeartbeatStatus, ProcessRole, ServerRuntimeState


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
        self.started_at = time.monotonic()

    def is_running(self) -> bool:
        return self.process.poll() is None


class StubbornWait:
    """A ``wait`` that times out once, so the supervisor escalates to kill."""

    def __init__(self, process: FakeProcess) -> None:
        self._process = process
        self.calls = 0

    def __call__(self, timeout: float | None = None) -> int:
        del timeout
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("still running")
        return self._process.returncode or 0


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


async def test_supervisor_logs_every_start_and_stop(monkeypatch: pytest.MonkeyPatch, captured_logs) -> None:
    """Starting and stopping a child must be visible in the Web process log."""
    monkeypatch.setattr(settings, "process_supervisor_enabled", True)
    launcher = FakeLauncher()
    supervisor = ProcessSupervisor(
        launcher=launcher,
        registry=ProcessHeartbeatRegistry(),
        required_workers=1,
        heartbeat_timeout_seconds=20,
    )

    await supervisor.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    started = [message for message in captured_logs if "Started supervised process" in message]
    assert len(started) == 2
    assert "role=scheduler" in started[0] and "role=worker" in started[1]

    await supervisor.stop()

    stopped = [message for message in captured_logs if "Stopped supervised process" in message]
    assert len(stopped) == 2
    assert all("killed=False" in message for message in stopped)
    assert {message.split("role=")[1].split(" ")[0] for message in stopped} == {"scheduler", "worker"}


async def test_supervisor_logs_a_stale_child_with_its_reason(monkeypatch: pytest.MonkeyPatch, captured_logs) -> None:
    """A stopped child is logged once, next to the reason it was stopped."""
    monkeypatch.setattr(settings, "process_supervisor_enabled", True)
    registry = ProcessHeartbeatRegistry()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await registry.record(
        ProcessHeartbeatIn(
            role=ProcessRole.WORKER,
            instance_id="worker-1",
            pid=201,
            status=ProcessHeartbeatStatus.RUNNING,
        ),
        now=now - timedelta(minutes=5),
    )
    supervisor = ProcessSupervisor(
        launcher=FakeLauncher(),
        registry=registry,
        required_workers=1,
        heartbeat_timeout_seconds=1,
    )
    managed = FakeManagedProcess(ProcessRole.WORKER, "worker-1", 201)
    managed.process.wait = StubbornWait(managed.process)
    supervisor._managed[ProcessRole.WORKER]["worker-1"] = managed

    await supervisor.run_once(now)

    assert any("heartbeat is stale; terminating" in message for message in captured_logs)
    assert any("did not stop after terminate; killing" in message for message in captured_logs)
    assert any(
        "Stopped supervised process" in message and "pid=201" in message and "killed=True" in message
        for message in captured_logs
    )


async def test_supervisor_persists_managed_child_pids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "process_supervisor_enabled", True)
    registry = ProcessHeartbeatRegistry()
    runtime_store = RuntimeStateStore(tmp_path / "runtime.json")
    await runtime_store.write(ServerRuntimeState(server_pid=123, port=6280))
    launcher = FakeLauncher()
    supervisor = ProcessSupervisor(
        launcher=launcher,
        registry=registry,
        runtime_state_store=runtime_store,
        required_workers=1,
        heartbeat_timeout_seconds=20,
    )

    await supervisor.run_once(datetime(2026, 1, 1, tzinfo=UTC))
    state = await runtime_store.read()

    assert state is not None
    assert len(state.scheduler_pids) == 1
    assert len(state.worker_pids) == 1
    await supervisor.stop()


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

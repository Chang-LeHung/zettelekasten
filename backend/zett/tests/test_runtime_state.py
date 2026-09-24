"""Runtime state and stop-controller behavior."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zett._compat import UTC
from zett.config import settings
from zett.infra.scheduler.runtime_state import (
    RuntimeProcessController,
    RuntimeStateStore,
    RuntimeWatchdog,
)
from zett.main import app
from zett.schemas import ProcessRole, ServerRuntimeState


async def test_runtime_state_round_trip_accepts_partial_records_and_removes_file(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")
    await store.write(
        ServerRuntimeState(
            server_pid=None,
            port=6280,
            scheduler_pids=[101],
            worker_pids=[201, 202],
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    loaded = await store.read()

    assert loaded is not None
    assert loaded.server_pid is None
    assert loaded.port == 6280
    assert loaded.scheduler_pids == [101]
    assert loaded.worker_pids == [201, 202]

    await store.remove()
    assert await store.read() is None
    assert not store.path.exists()


async def test_prepare_start_rejects_a_port_without_a_recorded_pid(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")
    await store.write(ServerRuntimeState(server_pid=None, port=6300))
    controller = RuntimeProcessController(store)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 6300))
    listener.listen()
    try:
        with pytest.raises(RuntimeError, match="no server PID"):
            await controller.prepare_start(port=6301)
    finally:
        listener.close()


async def test_prepare_start_cleans_stale_pid_state(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")
    await store.write(
        ServerRuntimeState(
            server_pid=999_999_999,
            port=6302,
            scheduler_pids=[999_999_998],
            worker_pids=[999_999_997],
        )
    )
    controller = RuntimeProcessController(store)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 6303))
    listener.listen()
    listener.close()

    state = await controller.prepare_start(port=6303)

    assert state.server_pid is None
    assert state.port == 6303
    assert await store.read() is None


async def test_stop_removes_state_when_recorded_processes_are_gone(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")
    await store.write(
        ServerRuntimeState(
            server_pid=999_999_996,
            port=6304,
            scheduler_pids=[999_999_995],
            worker_pids=[999_999_994],
        )
    )
    controller = RuntimeProcessController(store)

    stopped = await controller.stop(timeout=1)

    assert stopped is not None
    assert stopped.port == 6304
    assert await store.read() is None


async def test_stop_terminates_a_live_recorded_server(tmp_path: Path) -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        store = RuntimeStateStore(tmp_path / "runtime.json")
        await store.write(ServerRuntimeState(server_pid=process.pid, port=6305))
        controller = RuntimeProcessController(store)

        stopped = await controller.stop(timeout=2)

        assert stopped is not None
        assert stopped.server_pid == process.pid
        process.wait(timeout=1)
        assert await store.read() is None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


async def test_runtime_watchdog_accepts_only_complete_owned_state(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.json")

    async def on_orphaned(reason: str) -> None:
        del reason

    watchdog = RuntimeWatchdog(
        role=ProcessRole.SCHEDULER,
        pid=12345,
        store=store,
        interval_seconds=0.01,
        on_orphaned=on_orphaned,
    )

    assert "missing" in (await watchdog.check_once() or "")

    await store.write(ServerRuntimeState(server_pid=None, port=6280, scheduler_pids=[12345]))
    assert await watchdog.check_once() == "runtime state has no server_pid"

    await store.write(
        ServerRuntimeState(
            server_pid=os.getpid(),
            port=6280,
            scheduler_pids=[],
        )
    )
    assert "not registered" in (await watchdog.check_once() or "")

    await store.write(
        ServerRuntimeState(
            server_pid=os.getpid(),
            port=6280,
            scheduler_pids=[12345],
        )
    )
    assert await watchdog.check_once() is None


async def test_runtime_watchdog_exits_after_repeated_failures(tmp_path: Path) -> None:
    exited = threading.Event()

    async def on_orphaned(reason: str) -> None:
        del reason
        exited.set()

    watchdog = RuntimeWatchdog(
        role=ProcessRole.WORKER,
        pid=12345,
        store=RuntimeStateStore(tmp_path / "runtime.json"),
        interval_seconds=0.01,
        failure_threshold=2,
        on_orphaned=on_orphaned,
    )

    await watchdog.start()
    try:
        assert await asyncio.to_thread(exited.wait, 1)
    finally:
        await watchdog.stop()


def test_fastapi_lifespan_writes_and_removes_runtime_state() -> None:
    with TestClient(app):
        assert settings.runtime_state_path.is_file()
        payload = json.loads(settings.runtime_state_path.read_text())
        assert payload["server_pid"]
        assert payload["port"] == settings.port

    assert not settings.runtime_state_path.exists()

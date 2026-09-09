"""Concurrency tests for the process-owned agent storage."""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Self

import pytest

from zett.infra import agent_runtime


class FakeStorage:
    """Expose construction and closure counts without opening SQLite."""

    instances: list[Self] = []
    instances_lock = threading.Lock()

    def __init__(self, path: Path) -> None:
        self.path = path
        self.close_count = 0
        time.sleep(0.01)
        with self.instances_lock:
            self.instances.append(self)

    def close(self) -> None:
        self.close_count += 1


@pytest.fixture
def fake_runtime_storage(monkeypatch: pytest.MonkeyPatch):
    """Replace the real storage and reset process-global state around a test."""
    agent_runtime.close_agent_runtime_storage()
    FakeStorage.instances.clear()
    monkeypatch.setattr(agent_runtime, "SQLiteSessionStorage", FakeStorage)
    yield
    agent_runtime.close_agent_runtime_storage()


async def test_get_agent_runtime_storage_is_safe_for_concurrent_coroutines(fake_runtime_storage):
    ready = threading.Barrier(16)

    def get_after_barrier() -> FakeStorage:
        ready.wait()
        return agent_runtime.get_agent_runtime_storage()

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=16) as executor:
        storages = await asyncio.gather(*(loop.run_in_executor(executor, get_after_barrier) for _ in range(16)))

    assert len(FakeStorage.instances) == 1
    assert all(storage is storages[0] for storage in storages)


def test_path_change_and_close_are_serialized(fake_runtime_storage, monkeypatch: pytest.MonkeyPatch):
    first = agent_runtime.get_agent_runtime_storage()
    monkeypatch.setattr(agent_runtime.settings, "agent_database_path", Path("replacement.db"))

    second = agent_runtime.get_agent_runtime_storage()
    agent_runtime.close_agent_runtime_storage()

    assert second is not first
    assert first.close_count == 1
    assert second.close_count == 1

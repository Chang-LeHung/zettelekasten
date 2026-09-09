"""Tests for process-local named synchronization primitives."""

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from zett.infra.locks import synchronized


def test_same_name_serializes_different_decorated_functions() -> None:
    """Functions sharing a name must enter one common critical section."""
    worker_count = 12
    barrier = Barrier(worker_count)
    observation_lock = Lock()
    active_calls = 0
    peak_calls = 0

    def observe_critical_section() -> None:
        nonlocal active_calls, peak_calls
        with observation_lock:
            active_calls += 1
            peak_calls = max(peak_calls, active_calls)
        time.sleep(0.005)
        with observation_lock:
            active_calls -= 1

    @synchronized("shared-test-lock")
    def first() -> None:
        observe_critical_section()

    @synchronized("shared-test-lock")
    def second() -> None:
        observe_critical_section()

    def invoke(index: int) -> None:
        barrier.wait()
        (first if index % 2 == 0 else second)()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(invoke, range(worker_count)))

    assert peak_calls == 1


def test_different_names_do_not_share_a_lock() -> None:
    """Independent components must not block on unrelated lock names."""
    both_entered = Barrier(2)

    @synchronized("first-independent-lock")
    def first() -> None:
        both_entered.wait(timeout=1)

    @synchronized("second-independent-lock")
    def second() -> None:
        both_entered.wait(timeout=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(first), executor.submit(second))
        for future in futures:
            future.result(timeout=1)


def test_synchronized_preserves_the_wrapped_function_interface() -> None:
    """The decorator must remain transparent to callers and introspection."""

    @synchronized("signature-test-lock")
    def add(left: int, right: int = 1) -> int:
        """Add two integers."""
        return left + right

    assert add(2, right=3) == 5
    assert add.__name__ == "add"
    assert add.__doc__ == "Add two integers."
    assert str(inspect.signature(add)) == "(left: int, right: int = 1) -> int"


def test_synchronized_rejects_invalid_usage() -> None:
    """Empty names and coroutine functions would make locking ambiguous or unsafe."""
    with pytest.raises(ValueError, match="lock_name cannot be empty"):
        synchronized("  ")

    async def asynchronous() -> None:
        await asyncio.sleep(0)

    with pytest.raises(TypeError, match="synchronous functions only"):
        synchronized("async-test-lock")(asynchronous)

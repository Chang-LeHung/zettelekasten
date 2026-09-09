"""Small named-lock primitives for process-local synchronous critical sections."""

from collections.abc import Callable
from functools import wraps
from inspect import iscoroutinefunction
from threading import Lock, RLock
from typing import cast

_locks: dict[str, RLock] = {}
_registry_lock = Lock()


def synchronized[**ParametersT, ResultT](
    lock_name: str,
) -> Callable[[Callable[ParametersT, ResultT]], Callable[ParametersT, ResultT]]:
    """Serialize decorated synchronous functions sharing ``lock_name``.

    The registry lock protects creation of named locks. Each decorator then
    retains its resolved reentrant lock, so calls pay only the critical-section
    locking cost. Reentrancy allows one protected function to call another
    function using the same name on the same thread.

    Do not decorate coroutine functions: a thread lock held across ``await``
    can block an event-loop thread. Split asynchronous work from the short
    synchronous state mutation that needs protection instead.
    """
    normalized_name = lock_name.strip()
    if not normalized_name:
        raise ValueError("lock_name cannot be empty")
    with _registry_lock:
        lock = _locks.setdefault(normalized_name, RLock())

    def decorate(function: Callable[ParametersT, ResultT]) -> Callable[ParametersT, ResultT]:
        if iscoroutinefunction(function):
            raise TypeError("synchronized supports synchronous functions only")

        @wraps(function)
        def wrapped(*args: ParametersT.args, **kwargs: ParametersT.kwargs) -> ResultT:
            with lock:
                return function(*args, **kwargs)

        return cast(Callable[ParametersT, ResultT], wrapped)

    return decorate

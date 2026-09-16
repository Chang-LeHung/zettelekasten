"""Own the standalone zett-agent session database connection pool."""

from pathlib import Path
from threading import RLock

from zett_agent import SQLiteSessionStorage

from ..config import settings

_storage: SQLiteSessionStorage | None = None
_storage_path: Path | None = None
#: Storages superseded by a path change, closed by the next async shutdown.
_retired: list[SQLiteSessionStorage] = []
_storage_lock = RLock()


def get_agent_runtime_storage() -> SQLiteSessionStorage:
    """Return the package-owned store configured for this Zett process.

    The lock serializes lazy initialization, path changes, and shutdown across
    coroutine tasks and ordinary synchronous callers. Construction only
    prepares the path; ORM tables appear on the first awaited statement. No
    await point occurs while the lock is held.
    """
    global _storage, _storage_path
    with _storage_lock:
        path = settings.agent_database_path
        if _storage is None or _storage_path != path:
            if _storage is not None:
                # Closing needs the event loop this factory cannot await.
                _retired.append(_storage)
            _storage = SQLiteSessionStorage(path)
            _storage_path = path
        return _storage


async def close_agent_runtime_storage() -> None:
    """Dispose every connection pool this module created."""
    global _storage, _storage_path
    with _storage_lock:
        storages = [*_retired, _storage] if _storage is not None else list(_retired)
        _retired.clear()
        _storage = None
        _storage_path = None
    for storage in storages:
        await storage.close()

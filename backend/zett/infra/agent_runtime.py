"""Own the standalone zett-agent session database connection pool."""

from pathlib import Path

from zett_agent import SQLiteSessionStorage

from ..config import settings

_storage: SQLiteSessionStorage | None = None
_storage_path: Path | None = None


def get_agent_runtime_storage() -> SQLiteSessionStorage:
    """Return the package-owned store configured for this Zett process."""
    global _storage, _storage_path
    path = settings.agent_database_path
    if _storage is None or _storage_path != path:
        if _storage is not None:
            _storage.close()
        _storage = SQLiteSessionStorage(path)
        _storage_path = path
    return _storage


def close_agent_runtime_storage() -> None:
    """Dispose the lazily created agent database connection pool."""
    global _storage, _storage_path
    if _storage is not None:
        _storage.close()
    _storage = None
    _storage_path = None

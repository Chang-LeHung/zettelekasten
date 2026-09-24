"""Adapt Zett's SQLAlchemy key-value store to the plugin KVStorage contract."""

from __future__ import annotations

from ...plugins import JsonValue, KVStorage
from ..persistence.dao import KeyValueStorage, key_value_storage


class ZettKVStorage(KVStorage):
    """Persist plugin state in Zett's versioned key-value table."""

    def __init__(self, storage: KeyValueStorage = key_value_storage) -> None:
        self._storage = storage

    async def get(self, key: str) -> JsonValue | None:
        record = await self._storage.get(key)
        return record.value if record is not None else None

    async def set(self, key: str, value: JsonValue) -> None:
        await self._storage.update(key, value)

    async def delete(self, key: str) -> bool:
        return await self._storage.delete(key)

    async def iter_prefix(self, prefix: str) -> list[tuple[str, JsonValue]]:
        records = await self._storage.iter_prefix(prefix)
        return [(record.key, record.value) for record in records]


__all__ = ["ZettKVStorage"]

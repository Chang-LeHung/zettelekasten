"""Versioned JSON key-value storage implemented with SQLAlchemy."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from weakref import WeakKeyDictionary

from sqlalchemy import select
from zett_agent.ids import new_uuid7

from ...._compat import UTC
from ....schemas import JsonValue, KeyValueRecord
from ..database import session_scope
from ..tables import KeyValueRow


def _normalize_key(key: str) -> str:
    normalized = key.strip()
    if not normalized:
        raise ValueError("Key-value key cannot be empty")
    if len(normalized) > 500:
        raise ValueError("Key-value key cannot exceed 500 characters")
    return normalized


def _record(model: KeyValueRow) -> KeyValueRecord:
    """Detach and decode one ORM revision before its transaction closes."""
    created_at = model.created_at.replace(tzinfo=UTC) if model.created_at.tzinfo is None else model.created_at
    updated_at = model.updated_at.replace(tzinfo=UTC) if model.updated_at.tzinfo is None else model.updated_at
    return KeyValueRecord(
        id=model.id,
        key=model.key,
        value=json.loads(model.value),
        version=model.version,
        created_at=created_at,
        updated_at=updated_at,
    )


class KeyValueStorage:
    """Store one mutable JSON value under each unique indexed key.

    ``update`` creates version one for a new key. Later updates retain the
    record identity and creation time while replacing its value, incrementing
    its version, and refreshing its modification time.

    A read-modify-write needs one writer at a time. The lock is created per
    event loop so a shared instance can serve the application loop and the
    independent loops that tests create.
    """

    def __init__(self) -> None:
        self._write_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()

    def _write_lock(self) -> asyncio.Lock:
        """Return this loop's writer lock without binding other loops."""
        return self._write_locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())

    async def get(self, key: str) -> KeyValueRecord | None:
        """Return one current value, or ``None`` when its key is absent."""
        normalized = _normalize_key(key)
        async with session_scope() as session:
            statement = select(KeyValueRow).where(KeyValueRow.key == normalized)
            model = (await session.scalars(statement)).first()
            return _record(model) if model is not None else None

    async def update(self, key: str, value: JsonValue) -> KeyValueRecord:
        """Create or replace one value and return its incremented version.

        Databases created before the unique constraint was declared still only
        index the key, so the write stays a locked read-then-write instead of an
        ``ON CONFLICT`` upsert that requires a matching constraint.
        """
        normalized = _normalize_key(key)
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        async with self._write_lock(), session_scope() as session:
            now = datetime.now(UTC)
            model = (await session.scalars(select(KeyValueRow).where(KeyValueRow.key == normalized))).first()
            if model is None:
                model = KeyValueRow(
                    id=new_uuid7(),
                    key=normalized,
                    value=serialized,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
            else:
                model.value = serialized
                model.version += 1
                model.updated_at = now
            await session.flush()
            return _record(model)

    async def delete(self, key: str) -> bool:
        """Delete one key and report whether it existed."""
        normalized = _normalize_key(key)
        async with self._write_lock(), session_scope() as session:
            model = (await session.scalars(select(KeyValueRow).where(KeyValueRow.key == normalized))).first()
            if model is None:
                return False
            await session.delete(model)
            return True

    async def iter_prefix(self, prefix: str = "") -> list[KeyValueRecord]:
        """Return a key-sorted snapshot of current values under a prefix."""
        statement = select(KeyValueRow)
        if prefix:
            statement = statement.where(KeyValueRow.key.startswith(prefix, autoescape=True))
        statement = statement.order_by(KeyValueRow.key)
        async with session_scope() as session:
            return [_record(model) for model in await session.scalars(statement)]


key_value_storage = KeyValueStorage()

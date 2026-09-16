"""Versioned JSON key-value storage implemented with SQLAlchemy."""

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from zett_agent import new_uuid7

from ...schemas import JsonValue, KeyValueRecord
from ..database import session_scope
from ..models import KeyValueModel


def _normalize_key(key: str) -> str:
    normalized = key.strip()
    if not normalized:
        raise ValueError("Key-value key cannot be empty")
    if len(normalized) > 500:
        raise ValueError("Key-value key cannot exceed 500 characters")
    return normalized


def _record(model: KeyValueModel) -> KeyValueRecord:
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
    """

    async def get(self, key: str) -> KeyValueRecord | None:
        """Return one current value, or ``None`` when its key is absent."""
        normalized = _normalize_key(key)
        async with session_scope() as session:
            statement = select(KeyValueModel).where(KeyValueModel.key == normalized)
            model = (await session.scalars(statement)).first()
            return _record(model) if model is not None else None

    async def update(self, key: str, value: JsonValue) -> KeyValueRecord:
        """Create or replace one value and return its incremented version.

        The insert-or-update runs as one statement whose version increment is
        evaluated by SQLite, so concurrent callers cannot read the same version
        and no process-local lock is needed.
        """
        normalized = _normalize_key(key)
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        now = datetime.now(UTC)
        statement = (
            sqlite_insert(KeyValueModel)
            .values(
                id=new_uuid7(),
                key=normalized,
                value=serialized,
                version=1,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[KeyValueModel.key],
                set_={
                    "value": serialized,
                    "version": KeyValueModel.version + 1,
                    "updated_at": now,
                },
            )
            .returning(KeyValueModel)
        )
        async with session_scope() as session:
            model = (await session.scalars(statement)).one()
            return _record(model)

    async def delete(self, key: str) -> bool:
        """Delete one key and report whether it existed."""
        normalized = _normalize_key(key)
        async with session_scope() as session:
            model = (await session.scalars(select(KeyValueModel).where(KeyValueModel.key == normalized))).first()
            if model is None:
                return False
            await session.delete(model)
            return True

    async def iter_prefix(self, prefix: str = "") -> list[KeyValueRecord]:
        """Return a key-sorted snapshot of current values under a prefix."""
        statement = select(KeyValueModel)
        if prefix:
            statement = statement.where(KeyValueModel.key.startswith(prefix, autoescape=True))
        statement = statement.order_by(KeyValueModel.key)
        async with session_scope() as session:
            return [_record(model) for model in await session.scalars(statement)]


key_value_storage = KeyValueStorage()

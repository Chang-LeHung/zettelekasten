"""Versioned JSON key-value storage implemented with SQLAlchemy."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from threading import RLock

from sqlalchemy import select
from zett_agent import new_uuid7

from ...schemas import JsonValue, KeyValueRecord
from ..database import session_scope
from ..models import KeyValueModel

_write_lock = RLock()


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

    def get(self, key: str) -> KeyValueRecord | None:
        """Return one current value, or ``None`` when its key is absent."""
        normalized = _normalize_key(key)
        with session_scope() as session:
            statement = select(KeyValueModel).where(KeyValueModel.key == normalized)
            model = session.scalars(statement).first()
            return _record(model) if model is not None else None

    def update(self, key: str, value: JsonValue) -> KeyValueRecord:
        """Create or replace one value and return its incremented version."""
        normalized = _normalize_key(key)
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with _write_lock, session_scope() as session:
            now = datetime.now(UTC)
            model = session.scalars(select(KeyValueModel).where(KeyValueModel.key == normalized)).first()
            if model is None:
                model = KeyValueModel(
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
            session.flush()
            return _record(model)

    def delete(self, key: str) -> bool:
        """Delete one key and report whether it existed."""
        normalized = _normalize_key(key)
        with _write_lock, session_scope() as session:
            model = session.scalars(select(KeyValueModel).where(KeyValueModel.key == normalized)).first()
            if model is None:
                return False
            session.delete(model)
            return True

    def iter_prefix(self, prefix: str = "") -> Iterator[KeyValueRecord]:
        """Iterate a key-sorted snapshot of current values under a prefix."""
        statement = select(KeyValueModel)
        if prefix:
            statement = statement.where(KeyValueModel.key.startswith(prefix, autoescape=True))
        statement = statement.order_by(KeyValueModel.key)
        with session_scope() as session:
            snapshot = tuple(_record(model) for model in session.scalars(statement))
        return iter(snapshot)


key_value_storage = KeyValueStorage()

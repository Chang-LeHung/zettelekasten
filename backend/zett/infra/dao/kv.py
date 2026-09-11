"""Append-only, versioned JSON key-value storage implemented with SQLAlchemy."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from threading import RLock

from sqlalchemy import and_, func, select
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
    """Store JSON values as immutable revisions under non-unique indexed keys.

    ``set`` never updates an existing row. It appends a UUIDv7 revision whose
    version is one greater than the latest revision for that key. ``get`` and
    ``iter_prefix`` hide old revisions and expose only the latest value.
    """

    def get(self, key: str) -> KeyValueRecord | None:
        """Return the latest revision for one key, or ``None`` when absent."""
        normalized = _normalize_key(key)
        with session_scope() as session:
            statement = (
                select(KeyValueModel)
                .where(KeyValueModel.key == normalized)
                .order_by(KeyValueModel.version.desc(), KeyValueModel.id.desc())
                .limit(1)
            )
            model = session.scalars(statement).first()
            return _record(model) if model is not None else None

    def set(self, key: str, value: JsonValue) -> KeyValueRecord:
        """Append the next version for a key and return the stored revision."""
        normalized = _normalize_key(key)
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with _write_lock, session_scope() as session:
            latest_version = session.scalar(
                select(func.max(KeyValueModel.version)).where(KeyValueModel.key == normalized)
            )
            now = datetime.now(UTC)
            model = KeyValueModel(
                id=new_uuid7(),
                key=normalized,
                value=serialized,
                version=(latest_version or 0) + 1,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return _record(model)

    def delete(self, key: str) -> bool:
        """Delete every revision for one key and report whether any existed."""
        normalized = _normalize_key(key)
        with _write_lock, session_scope() as session:
            models = list(session.scalars(select(KeyValueModel).where(KeyValueModel.key == normalized)))
            for model in models:
                session.delete(model)
            return bool(models)

    def iter_prefix(self, prefix: str = "") -> Iterator[KeyValueRecord]:
        """Iterate a key-sorted snapshot of latest revisions under a prefix.

        The ordinary non-unique key index narrows prefix scans. A grouped
        subquery selects the greatest version for each matching key, ensuring
        superseded rows do not leak through this current-value interface.
        """
        latest = select(
            KeyValueModel.key.label("key"),
            func.max(KeyValueModel.version).label("version"),
        )
        if prefix:
            latest = latest.where(KeyValueModel.key.startswith(prefix, autoescape=True))
        latest_versions = latest.group_by(KeyValueModel.key).subquery()
        statement = (
            select(KeyValueModel)
            .join(
                latest_versions,
                and_(
                    KeyValueModel.key == latest_versions.c.key,
                    KeyValueModel.version == latest_versions.c.version,
                ),
            )
            .order_by(KeyValueModel.key)
        )
        with session_scope() as session:
            snapshot = tuple(_record(model) for model in session.scalars(statement))
        return iter(snapshot)


key_value_storage = KeyValueStorage()

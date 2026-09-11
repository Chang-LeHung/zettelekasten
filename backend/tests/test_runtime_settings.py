"""Tests for SQLite-backed versioned runtime settings."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine

from zett.infra.dao.kv import KeyValueStorage
from zett.infra.database import session_scope
from zett.infra.models import KeyValueModel
from zett.main import app


def test_key_value_storage_appends_versions_and_reads_latest_revision() -> None:
    storage = KeyValueStorage()

    first = storage.set("settings.example", {"label": "value-中文", "enabled": True})
    second = storage.set("settings.example", {"label": "updated", "count": 2})

    assert UUID(first.id).version == 7
    assert UUID(second.id).version == 7
    assert first.id != second.id
    assert first.version == 1
    assert second.version == 2
    assert storage.get("settings.example") == second

    with session_scope() as session:
        revisions = list(
            session.scalars(
                select(KeyValueModel).where(KeyValueModel.key == "settings.example").order_by(KeyValueModel.version)
            )
        )
        assert [revision.version for revision in revisions] == [1, 2]
        assert [json.loads(revision.value) for revision in revisions] == [
            {"label": "value-中文", "enabled": True},
            {"label": "updated", "count": 2},
        ]


def test_key_value_storage_prefix_returns_only_latest_values_in_key_order() -> None:
    storage = KeyValueStorage()
    storage.set("providers.second", {"value": 1})
    storage.set("settings.runtime", {"value": "runtime"})
    storage.set("providers.first", {"value": "first"})
    storage.set("providers.second", {"value": 2})
    storage.set("providers_%literal", {"value": "literal"})

    providers = list(storage.iter_prefix("providers."))
    assert [(record.key, record.version, record.value) for record in providers] == [
        ("providers.first", 1, {"value": "first"}),
        ("providers.second", 2, {"value": 2}),
    ]
    assert [record.key for record in storage.iter_prefix()] == [
        "providers.first",
        "providers.second",
        "providers_%literal",
        "settings.runtime",
    ]
    assert list(storage.iter_prefix("missing.")) == []
    assert [record.key for record in storage.iter_prefix("providers_%")] == ["providers_%literal"]


def test_key_value_storage_delete_removes_all_revisions() -> None:
    storage = KeyValueStorage()
    storage.set("settings.example", 1)
    storage.set("settings.example", 2)

    assert storage.delete("settings.example") is True
    assert storage.delete("settings.example") is False
    assert storage.get("settings.example") is None


def test_key_value_storage_serializes_concurrent_versions() -> None:
    storage = KeyValueStorage()

    with ThreadPoolExecutor(max_workers=4) as executor:
        records = list(executor.map(lambda value: storage.set("concurrent.key", value), range(8)))

    assert sorted(record.version for record in records) == list(range(1, 9))
    latest = storage.get("concurrent.key")
    assert latest is not None
    assert latest.version == 8


def test_key_value_storage_validates_keys_and_json_values() -> None:
    storage = KeyValueStorage()

    with pytest.raises(ValueError, match="cannot be empty"):
        storage.get("  ")
    with pytest.raises(ValueError, match="cannot exceed"):
        storage.set("x" * 501, None)
    with pytest.raises((TypeError, ValueError)):
        storage.set("invalid.value", {"not_json": object()})  # type: ignore[dict-item]


def test_key_column_has_a_non_unique_sqlite_index(isolated_database: Engine) -> None:
    key_column = KeyValueModel.__table__.c.key

    assert key_column.index is True
    assert key_column.unique is not True
    indexes = inspect(isolated_database).get_indexes(KeyValueModel.__tablename__)
    key_index = next(index for index in indexes if index["column_names"] == ["key"])
    assert key_index["unique"] == 0


def test_runtime_settings_http_lifecycle_uses_defaults_and_persists_updates() -> None:
    with TestClient(app) as client:
        assert client.get("/api/settings").json() == {"max_message_images": 32}

        updated = client.put("/api/settings", json={"max_message_images": 48})
        assert updated.status_code == 200
        assert updated.json() == {"max_message_images": 48}
        assert client.get("/api/settings").json() == {"max_message_images": 48}

        assert client.put("/api/settings", json={"max_message_images": 0}).status_code == 422
        assert client.put("/api/settings", json={"max_message_images": 257}).status_code == 422

    with session_scope() as session:
        revisions = list(session.scalars(select(KeyValueModel).where(KeyValueModel.key == "settings.runtime")))
        assert len(revisions) == 1
        assert revisions[0].version == 1
        assert json.loads(revisions[0].value) == {"max_message_images": 48}

"""Tests for SQLite-backed versioned runtime settings."""

import asyncio
import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from zett.infra import database
from zett.infra.dao.kv import KeyValueStorage
from zett.infra.database import session_scope
from zett.infra.models import KeyValueModel
from zett.main import app


async def test_key_value_storage_updates_one_record_and_increments_its_version() -> None:
    storage = KeyValueStorage()

    first = await storage.update("settings.example", {"label": "value-中文", "enabled": True})
    second = await storage.update("settings.example", {"label": "updated", "count": 2})

    assert UUID(first.id).version == 7
    assert first.id == second.id
    assert first.version == 1
    assert second.version == 2
    assert await storage.get("settings.example") == second

    async with session_scope() as session:
        rows = await session.scalars(select(KeyValueModel).where(KeyValueModel.key == "settings.example"))
        records = list(rows)
        assert len(records) == 1
        assert records[0].version == 2
        assert json.loads(records[0].value) == {"label": "updated", "count": 2}


async def test_key_value_storage_prefix_returns_only_latest_values_in_key_order() -> None:
    storage = KeyValueStorage()
    await storage.update("providers.second", {"value": 1})
    await storage.update("settings.runtime", {"value": "runtime"})
    await storage.update("providers.first", {"value": "first"})
    await storage.update("providers.second", {"value": 2})
    await storage.update("providers_%literal", {"value": "literal"})

    providers = await storage.iter_prefix("providers.")
    assert [(record.key, record.version, record.value) for record in providers] == [
        ("providers.first", 1, {"value": "first"}),
        ("providers.second", 2, {"value": 2}),
    ]
    assert [record.key for record in await storage.iter_prefix()] == [
        "providers.first",
        "providers.second",
        "providers_%literal",
        "settings.runtime",
    ]
    assert await storage.iter_prefix("missing.") == []
    assert [record.key for record in await storage.iter_prefix("providers_%")] == ["providers_%literal"]


async def test_key_value_storage_delete_removes_the_record() -> None:
    storage = KeyValueStorage()
    await storage.update("settings.example", 1)
    await storage.update("settings.example", 2)

    assert await storage.delete("settings.example") is True
    assert await storage.delete("settings.example") is False
    assert await storage.get("settings.example") is None


async def test_key_value_update_works_on_a_schema_without_a_unique_index(tmp_path, monkeypatch) -> None:
    """Databases created before the unique key constraint only index the column."""
    legacy_engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(tmp_path / "legacy.db")),
        poolclass=NullPool,
    )
    monkeypatch.setattr(database, "session_factory", async_sessionmaker(legacy_engine, expire_on_commit=False))
    async with legacy_engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE key_values (
                    id VARCHAR(36) NOT NULL,
                    "key" VARCHAR(500) NOT NULL,
                    value TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        await connection.execute(text('CREATE INDEX ix_key_values_key ON key_values ("key")'))

    storage = KeyValueStorage()
    try:
        first = await storage.update("sessions.model.legacy", {"value": 1})
        second = await storage.update("sessions.model.legacy", {"value": 2})

        assert (first.version, second.version) == (1, 2)
        assert first.id == second.id
        latest = await storage.get("sessions.model.legacy")
        assert latest is not None and latest.value == {"value": 2}
    finally:
        await legacy_engine.dispose()


async def test_key_value_storage_serializes_concurrent_versions() -> None:
    storage = KeyValueStorage()

    records = await asyncio.gather(*(storage.update("concurrent.key", value) for value in range(8)))

    assert sorted(record.version for record in records) == list(range(1, 9))
    latest = await storage.get("concurrent.key")
    assert latest is not None
    assert latest.version == 8


async def test_key_value_storage_validates_keys_and_json_values() -> None:
    storage = KeyValueStorage()

    with pytest.raises(ValueError, match="cannot be empty"):
        await storage.get("  ")
    with pytest.raises(ValueError, match="cannot exceed"):
        await storage.update("x" * 501, None)
    with pytest.raises((TypeError, ValueError)):
        await storage.update("invalid.value", {"not_json": object()})  # type: ignore[dict-item]


def test_key_column_has_a_unique_sqlite_index(isolated_database: Path) -> None:
    key_column = KeyValueModel.__table__.c.key

    assert key_column.index is True
    assert key_column.unique is True
    with sqlite3.connect(isolated_database) as connection:
        indexes = connection.execute(f"pragma index_list({KeyValueModel.__tablename__})").fetchall()
        unique_key_index = next(
            row[1]
            for row in indexes
            if row[2] == 1
            and [column[2] for column in connection.execute(f"pragma index_info({row[1]})").fetchall()] == ["key"]
        )
    assert unique_key_index == "ix_key_values_key"


async def test_runtime_settings_http_lifecycle_uses_defaults_and_persists_updates() -> None:
    with TestClient(app) as client:
        assert client.get("/api/settings").json() == {
            "max_message_images": 32,
            "max_turn_iterations": 36,
            "compaction_max_tokens": 128_000,
            "compaction_keep_recent_tokens": 32_000,
        }

        updated = client.put(
            "/api/settings",
            json={
                "max_message_images": 48,
                "max_turn_iterations": 64,
                "compaction_max_tokens": 512_000,
                "compaction_keep_recent_tokens": 64_000,
            },
        )
        assert updated.status_code == 200
        assert updated.json() == {
            "max_message_images": 48,
            "max_turn_iterations": 64,
            "compaction_max_tokens": 512_000,
            "compaction_keep_recent_tokens": 64_000,
        }
        assert client.get("/api/settings").json() == {
            "max_message_images": 48,
            "max_turn_iterations": 64,
            "compaction_max_tokens": 512_000,
            "compaction_keep_recent_tokens": 64_000,
        }

        assert client.put("/api/settings", json={"max_message_images": 0}).status_code == 422
        assert client.put("/api/settings", json={"max_message_images": 257}).status_code == 422
        assert client.put("/api/settings", json={"max_turn_iterations": 0}).status_code == 422
        assert client.put("/api/settings", json={"max_turn_iterations": 257}).status_code == 422
        assert (
            client.put(
                "/api/settings",
                json={"compaction_max_tokens": 32_000, "compaction_keep_recent_tokens": 32_000},
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/settings",
                json={"compaction_max_tokens": 801_000, "compaction_keep_recent_tokens": 32_000},
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/settings",
                json={"compaction_max_tokens": 800_000, "compaction_keep_recent_tokens": 31_000},
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/settings",
                json={"compaction_max_tokens": 800_000, "compaction_keep_recent_tokens": 257_000},
            ).status_code
            == 422
        )

    async with session_scope() as session:
        rows = await session.scalars(select(KeyValueModel).where(KeyValueModel.key == "settings.runtime"))
        revisions = list(rows)
        assert len(revisions) == 1
        assert revisions[0].version == 1
        assert json.loads(revisions[0].value) == {
            "max_message_images": 48,
            "max_turn_iterations": 64,
            "compaction_max_tokens": 512_000,
            "compaction_keep_recent_tokens": 64_000,
        }

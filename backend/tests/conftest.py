from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from zett_agent import AssistantMessage, ModelEvent, ModelRequest, ModelResponse

from zett import config
from zett.application import provider_connections
from zett.application.health import process_heartbeat_registry
from zett.infra import database
from zett.infra.artifacts.search import ensure_artifact_search
from zett.infra.files import object_store as object_store_module
from zett.infra.files.object_store import LocalObjectStore
from zett.infra.tables import Base


@pytest.fixture(autouse=True)
def isolated_provider_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provider lifecycle tests deterministic and offline."""

    class ProbeModel:
        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="OK")))

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(provider_connections, "create_model", lambda _connection: ProbeModel())


@pytest.fixture(autouse=True)
async def isolated_database(tmp_path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Run every test against a fresh SQLite database outside the user's data directory."""
    database_path = tmp_path / "zett-test.db"
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(database_path)),
        poolclass=NullPool,
    )
    monkeypatch.setattr(config.settings, "database_path", database_path)
    monkeypatch.setattr(config.settings, "agent_database_path", tmp_path / "agent-test.db")
    monkeypatch.setattr(config.settings, "storage_root", tmp_path)
    monkeypatch.setattr(config.settings, "provider_key_path", tmp_path / "provider.key")
    monkeypatch.setattr(config.settings, "log_directory", tmp_path / "logs")
    monkeypatch.setattr(config.settings, "process_supervisor_enabled", False)
    monkeypatch.setattr(object_store_module, "_object_store", LocalObjectStore(tmp_path))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "session_factory", async_sessionmaker(engine, expire_on_commit=False))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await ensure_artifact_search(connection)
    await process_heartbeat_registry.clear()
    yield database_path
    from zett.infra.agent.runtime import close_agent_runtime_storage

    await close_agent_runtime_storage()
    await engine.dispose()

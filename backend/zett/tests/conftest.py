import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from zett_agent import AssistantMessage, ModelEvent, ModelRequest, ModelResponse

from zett import config
from zett.agent import config as agent_config
from zett.application.health import process_heartbeat_registry
from zett.application.providers import provider_connections
from zett.infra.artifacts.search import ensure_artifact_search
from zett.infra.files import object_store as object_store_module
from zett.infra.files.object_store import LocalObjectStore
from zett.infra.persistence import database
from zett.infra.persistence.tables import Base


@pytest.fixture
def captured_logs() -> Iterator[list[str]]:
    """Collect Zett log messages straight from the namespace logger.

    ``configure_logging`` turns propagation off for the ``zett`` logger, so a
    root-level capture misses these records and a test would pass or fail purely
    by file order. Attaching a handler to the namespace logger avoids that.

    Tests that start the app through ``TestClient`` must read the configured log
    file instead: app startup calls ``configure_logging``, which replaces every
    handler on the namespace logger, including the one added here.
    """
    messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("zett")
    handler = Capture()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


@pytest.fixture(autouse=True)
def isolated_skill_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provision built-in skills into a temporary root instead of the real home."""
    monkeypatch.setattr(agent_config, "DEFAULT_ZETT_SKILL_ROOTS", (str(tmp_path / "skills"),))


@pytest.fixture(autouse=True)
def isolated_git_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every git command deterministic across developer machines and CI."""
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")


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
    monkeypatch.setattr(config.settings, "runtime_state_path", tmp_path / "runtime.json")
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

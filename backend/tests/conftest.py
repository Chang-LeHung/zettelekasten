from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from zett import config
from zett.infra import database
from zett.infra.models import Base


@pytest.fixture(autouse=True)
async def isolated_database(tmp_path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Engine]:
    """Run every test against a fresh SQLite database outside the user's data directory."""
    database_path = tmp_path / "zett-test.db"
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    monkeypatch.setattr(config.settings, "database_path", database_path)
    monkeypatch.setattr(config.settings, "agent_database_path", tmp_path / "agent-test.db")
    monkeypatch.setattr(config.settings, "asset_directory", tmp_path / "assets")
    monkeypatch.setattr(config.settings, "artifact_directory", tmp_path / "artifacts")
    monkeypatch.setattr(config.settings, "provider_key_path", tmp_path / "provider.key")
    monkeypatch.setattr(config.settings, "log_directory", tmp_path / "logs")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    yield engine
    from zett.infra.agent_runtime import close_agent_runtime_storage

    await close_agent_runtime_storage()
    engine.dispose()

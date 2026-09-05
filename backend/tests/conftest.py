from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from kcs import config
from kcs.infra import database
from kcs.infra.models import Base


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """Run every test against a fresh SQLite database outside the user's data directory."""
    database_path = tmp_path / "cards-test.db"
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    monkeypatch.setattr(config.settings, "database_path", database_path)
    monkeypatch.setattr(config.settings, "agent_database_path", tmp_path / "agent-test.db")
    monkeypatch.setattr(config.settings, "asset_directory", tmp_path / "assets")
    monkeypatch.setattr(config.settings, "log_directory", tmp_path / "logs")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(engine)
    yield engine
    from kcs.infra.agent_runtime import close_agent_runtime_storage

    close_agent_runtime_storage()
    engine.dispose()

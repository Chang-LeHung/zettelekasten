"""Preparing the schema when several processes start against one database."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from zett import config
from zett.infra.persistence import database


async def _fresh_engine(path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)), poolclass=NullPool)
    monkeypatch.setattr(config.settings, "database_path", path)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "session_factory", async_sessionmaker(engine, expire_on_commit=False))
    return engine


async def test_concurrent_starts_prepare_one_schema_without_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server, scheduler, and worker all call ``init_db`` at once on a first start.

    Each schema step looks at what exists and then changes it. Interleaved, two
    processes both saw an index and both dropped it, and the loser died with
    ``no such index`` and no log. Eight at once, repeated, makes that window wide.
    """
    for round_number in range(4):
        engine = await _fresh_engine(tmp_path / f"shared-{round_number}.db", monkeypatch)
        results = await asyncio.gather(*(database.init_db() for _ in range(8)), return_exceptions=True)
        failures = [result for result in results if isinstance(result, BaseException)]
        assert failures == [], f"round {round_number}: {failures[0]!r}"

        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        assert {"session_artifacts", "tags"} <= tables
        await engine.dispose()


async def test_a_lock_that_outlasts_the_wait_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.exc import OperationalError

    await _fresh_engine(tmp_path / "retry.db", monkeypatch)
    monkeypatch.setattr(database, "INIT_RETRY_SECONDS", 0.001)
    real = database._prepare_schema
    attempts: list[int] = []

    async def flaky() -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise OperationalError("BEGIN IMMEDIATE", {}, Exception("database is locked"))
        await real()

    monkeypatch.setattr(database, "_prepare_schema", flaky)
    await database.init_db()
    assert len(attempts) == 3


async def test_an_error_that_is_not_a_lock_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.exc import OperationalError

    await _fresh_engine(tmp_path / "broken.db", monkeypatch)
    attempts: list[int] = []

    async def broken() -> None:
        attempts.append(1)
        raise OperationalError("CREATE TABLE", {}, Exception("disk I/O error"))

    monkeypatch.setattr(database, "_prepare_schema", broken)
    with pytest.raises(OperationalError):
        await database.init_db()
    assert len(attempts) == 1


async def test_a_failed_step_rolls_the_whole_preparation_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = await _fresh_engine(tmp_path / "rollback.db", monkeypatch)

    async def explode(_connection: object) -> None:
        raise RuntimeError("step failed")

    monkeypatch.setattr(database, "ensure_indexes", explode)
    with pytest.raises(RuntimeError, match="step failed"):
        await database.init_db()

    # Nothing half-made is left behind, and the write lock is released for the next process.
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert tables == set()
    monkeypatch.undo()

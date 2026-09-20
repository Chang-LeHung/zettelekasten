"""Idempotent schema upgrades for databases created by an older version."""

from sqlalchemy import text

from zett.infra import database
from zett.infra.database import init_db, session_scope


async def _columns(table: str) -> set[str]:
    async with database.engine.begin() as connection:
        rows = (await connection.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    return {row[1] for row in rows}


async def test_init_db_adds_the_artifact_draft_column_once() -> None:
    await init_db()
    async with database.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE session_artifacts DROP COLUMN draft_content_json"))

    assert "draft_content_json" not in await _columns("session_artifacts")

    await init_db()
    await init_db()

    assert "draft_content_json" in await _columns("session_artifacts")


async def test_ensure_columns_keeps_existing_artifact_rows_readable() -> None:
    await init_db()
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO session_artifacts "
                "(id, session_id, artifact_type, status, title, content_json, raw_content, version, metadata, "
                "created_at, updated_at) "
                "VALUES ('legacy', 'session', 1, 1, 'Legacy card', '{\"artifact_type\": \"card\", "
                '"title": "Legacy card", "content": "Body"}\', NULL, 1, \'{}\', '
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
    async with database.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE session_artifacts DROP COLUMN draft_content_json"))

    await init_db()

    from zett.infra.dao import artifact_storage

    artifact = await artifact_storage.get("legacy")
    assert artifact is not None
    assert artifact.content is not None and artifact.content.title == "Legacy card"
    assert artifact.draft_content is None

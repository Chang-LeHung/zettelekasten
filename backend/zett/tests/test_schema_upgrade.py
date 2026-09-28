"""Idempotent schema upgrades for databases created by an older version."""

from datetime import datetime, timedelta

from sqlalchemy import text

from zett._compat import UTC
from zett.infra.persistence import database
from zett.infra.persistence.dao import scheduled_task_storage
from zett.infra.persistence.database import init_db, session_scope
from zett.schemas import (
    CronSchedule,
    ScheduledTaskAction,
    ScheduledTaskWrite,
)


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

    from zett.infra.persistence.dao import artifact_storage

    artifact = await artifact_storage.get("legacy")
    assert artifact is not None
    assert artifact.content is not None and artifact.content.title == "Legacy card"
    assert artifact.draft_content is None


async def test_init_db_removes_the_retired_scheduled_task_misfire_column_once() -> None:
    await init_db()
    async with database.engine.begin() as connection:
        await connection.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN misfire_grace_seconds INTEGER NOT NULL"))

    assert "misfire_grace_seconds" in await _columns("scheduled_tasks")

    await init_db()
    await init_db()

    assert "misfire_grace_seconds" not in await _columns("scheduled_tasks")
    now = datetime.now(UTC)
    created = await scheduled_task_storage.create(
        ScheduledTaskWrite(
            name="After migration",
            enabled=True,
            schedule=CronSchedule(expression="0 9 * * *", timezone="UTC"),
            action=ScheduledTaskAction(kind="probe", payload={}),
            next_run_at=now + timedelta(minutes=1),
            timeout_seconds=60,
            overlap_policy="skip",
        )
    )
    assert created.name == "After migration"


async def test_init_db_rebuilds_the_tag_uniqueness_of_an_older_database() -> None:
    """A database from before per-library collections keeps its tags.

    PostgreSQL and SQLite alike cannot alter a constraint in place, so the shape
    this release needs — one path per library instead of one path overall — is
    reached by adding the missing column and swapping the unique index. The rows
    that predate it were all artifact collections, and they stay.
    """
    await init_db()
    async with database.engine.begin() as connection:
        # Rebuild the shape the earlier release wrote: SQLite cannot drop a column
        # an index and a unique constraint both name.
        await connection.execute(text("DROP TABLE IF EXISTS tag_links"))
        await connection.execute(text("DROP TABLE IF EXISTS tags"))
        await connection.execute(
            text(
                "CREATE TABLE tags ("
                "id VARCHAR(36) NOT NULL PRIMARY KEY, "
                "path VARCHAR(500) NOT NULL, "
                "normalized_path VARCHAR(500) NOT NULL, "
                "name VARCHAR(100) NOT NULL, "
                "parent_id VARCHAR(36), description TEXT, color VARCHAR(32), "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
        await connection.execute(text("CREATE UNIQUE INDEX ix_tags_normalized_path ON tags (normalized_path)"))
        await connection.execute(
            text(
                "INSERT INTO tags (id, path, normalized_path, name, parent_id, description, color, created_at, "
                "updated_at) VALUES ('legacy', 'Engineering', 'engineering', 'Engineering', NULL, NULL, NULL, "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )

    assert "target_type" not in await _columns("tags")

    await init_db()
    await init_db()

    assert "target_type" in await _columns("tags")
    async with database.engine.begin() as connection:
        indexes = {row[1]: row[2] for row in (await connection.execute(text("PRAGMA index_list(tags)"))).fetchall()}
    assert indexes["ix_tags_normalized_path"] == 0
    assert indexes["uq_tags_target_type_normalized_path"] == 1

    from zett.application.tags.tagging import tag_service
    from zett.schemas import TagTargetType

    # The legacy node is an artifact collection, and the same path can now be
    # created as a file collection instead of colliding with it.
    artifact_tag = await tag_service.create_path("Engineering", TagTargetType.ARTIFACT)
    assert artifact_tag.id == "legacy"
    file_tag = await tag_service.create_path("Engineering", TagTargetType.ASSET)
    assert file_tag.id != artifact_tag.id

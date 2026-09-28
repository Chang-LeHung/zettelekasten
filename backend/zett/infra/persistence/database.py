"""Asynchronous SQLAlchemy transactions for application records.

Artifacts, assets, tags, providers, and key-value settings live in the
application database; Agent session history stays in the separate zett-agent
database. Both are asynchronous, so routes await one engine each instead of
hopping through a worker thread per DAO call.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateColumn, CreateIndex

from ...config import settings
from ..artifacts.search import ensure_artifact_search
from ..log import get_logger
from .tables import Base

logger = get_logger(__name__)

#: NullPool keeps every connection inside the loop that opened it, matching the
#: Agent session storage and allowing tests to swap paths per event loop.
engine = create_async_engine(
    URL.create("sqlite+aiosqlite", database=str(settings.database_path)),
    poolclass=NullPool,
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _configure_sqlite_connection(dbapi_connection: object, _: object) -> None:
    """Use WAL and wait briefly when the scheduler and Web process both write."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


async def ensure_indexes(connection: AsyncConnection) -> None:
    """Add indexes missing from databases created by an older application version."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            await connection.execute(CreateIndex(index, if_not_exists=True))


#: Columns added after the first release, as ``(table, column)`` names. Their
#: types come from the ORM model so the DDL cannot drift from the schema.
_ADDED_COLUMNS = (("session_artifacts", "draft_content_json"),)

#: Columns removed from the ORM after an earlier release. ``create_all`` does
#: not drop existing columns, so old NOT NULL columns continue to reject inserts
#: that no longer provide a value. Name them here so startup performs the SQLite
#: DDL migration idempotently before the application serves requests.
_REMOVED_COLUMNS = (("scheduled_tasks", "misfire_grace_seconds"),)

#: Columns an earlier release left out whose existing rows need a value: SQLite
#: refuses ``ADD COLUMN ... NOT NULL`` without a default, and every tag that
#: predates per-library collection trees was an artifact one.
_ADDED_COLUMNS_WITH_DEFAULT = (("tags", "target_type", "INTEGER NOT NULL DEFAULT 1"),)

#: Uniqueness rules that changed shape, as ``(table, index to drop, columns)``.
#: SQLite cannot alter a constraint in place and ``create_all`` never touches an
#: existing table, so the old unique index is dropped and an equivalent unique
#: index for the new rule is created instead; the rows stay where they are.
_REPLACED_UNIQUE_INDEXES = (("tags", "ix_tags_normalized_path", ("target_type", "normalized_path")),)


async def ensure_columns(connection: AsyncConnection) -> None:
    """Add columns missing from databases created by an older application version.

    ``create_all`` never alters an existing table, and SQLite cannot express this
    through the ORM, so the DDL stays here. Adding a nullable column needs no
    table rebuild, and the ``PRAGMA`` check keeps reruns idempotent.
    """
    for table_name, column_name in _ADDED_COLUMNS:
        existing = {row[1] for row in (await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")).fetchall()}
        if column_name in existing:
            continue
        column = Base.metadata.tables[table_name].columns[column_name]
        definition = CreateColumn(column).compile(dialect=connection.dialect)
        await connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


async def remove_columns(connection: AsyncConnection) -> None:
    """Drop columns retired from the ORM by an earlier application version."""
    for table_name, column_name in _REMOVED_COLUMNS:
        existing = {row[1] for row in (await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")).fetchall()}
        if column_name not in existing:
            continue
        await connection.exec_driver_sql(f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"')


async def init_db() -> None:
    """Create the current schema and repair the shapes an older release wrote.

    The steps run in this order for a reason: a column has to exist before an
    index can name it, and a uniqueness rule a newer release changed has to be
    replaced before ``ensure_indexes`` sees the old index under the same name.
    """
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await add_columns_with_default(connection)
        await ensure_columns(connection)
        await replace_unique_indexes(connection)
        await ensure_indexes(connection)
        await remove_columns(connection)
        await ensure_artifact_search(connection)


async def add_columns_with_default(connection: AsyncConnection) -> None:
    """Add one column an earlier release lacked, filling in its legacy value."""
    for table_name, column_name, definition in _ADDED_COLUMNS_WITH_DEFAULT:
        existing = {row[1] for row in (await connection.exec_driver_sql(f"PRAGMA table_info({table_name})")).fetchall()}
        if column_name in existing:
            continue
        await connection.exec_driver_sql(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}')
        logger.info(
            "Added a column an older database lacked; table=%s column=%s default=%s",
            table_name,
            column_name,
            definition,
        )


async def replace_unique_indexes(connection: AsyncConnection) -> None:
    """Swap a uniqueness rule an earlier release enforced differently."""
    for table_name, index_name, columns in _REPLACED_UNIQUE_INDEXES:
        existing = {row[1] for row in (await connection.exec_driver_sql(f"PRAGMA index_list({table_name})")).fetchall()}
        if index_name not in existing:
            continue
        await connection.exec_driver_sql(f'DROP INDEX "{index_name}"')
        names = ", ".join(f'"{column}"' for column in columns)
        replacement = f"uq_{table_name}_{'_'.join(columns)}"
        await connection.exec_driver_sql(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{replacement}" ON "{table_name}" ({names})'
        )
        logger.info(
            "Replaced a uniqueness rule an older database carried; table=%s index=%s columns=%s",
            table_name,
            replacement,
            ",".join(columns),
        )


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """Commit successful operations and roll back failed ones."""
    async with session_factory() as session, session.begin():
        yield session

"""Asynchronous SQLAlchemy transactions for application records.

Artifacts, assets, tags, providers, and key-value settings live in the
application database; Agent session history stays in the separate zett-agent
database. Both are asynchronous, so routes await one engine each instead of
hopping through a worker thread per DAO call.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event, or_
from sqlalchemy import update as sql_update
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateColumn, CreateIndex

from ...config import settings
from ...schemas import CARD_STATUSES, ArtifactType, default_status
from ..artifacts.search import ensure_artifact_search
from ..log import get_logger
from .tables import CARD_STATUS_TO_CODE, TYPE_TO_CODE, Base, SessionArtifactRow

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
_ADDED_COLUMNS = (("session_artifacts", "draft_content_json"), ("session_artifacts", "card_status"))

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


#: The server, the scheduler, and every worker prepare the same schema when they start
#: together. Each step looks at what exists and then changes it, so two of them
#: interleaving can both see an index and both try to drop it; the loser crashed with
#: "no such index" and was restarted by the supervisor with no trace of why. Taking the
#: write lock before the first look makes the look and the change one atomic step, and
#: the process that waits then finds the work already done.
INIT_ATTEMPTS = 8
INIT_RETRY_SECONDS = 0.25


async def init_db() -> None:
    """Create the current schema and repair the shapes an older release wrote.

    Several processes run this at once on a first start, so the preparation is
    serialized across them, and a lock that outlasts ``busy_timeout`` is retried
    instead of crashing the process that waited.
    """
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, INIT_ATTEMPTS + 1):
        try:
            await _prepare_schema()
            return
        except OperationalError as error:
            if "locked" not in str(error).lower() or attempt == INIT_ATTEMPTS:
                raise
            logger.info("Schema preparation waited on a locked database; attempt=%d/%d", attempt, INIT_ATTEMPTS)
            await asyncio.sleep(INIT_RETRY_SECONDS * attempt)


async def _prepare_schema() -> None:
    """Run the schema steps in one write transaction taken up front.

    ``BEGIN IMMEDIATE`` has no ORM equivalent: SQLAlchemy's own transaction
    starts deferred, as a reader, and is refused the moment it turns into a
    writer behind another process. The steps run in this order for a reason: a
    column has to exist before an index can name it, and a uniqueness rule a
    newer release changed has to be replaced before ``ensure_indexes`` sees the
    old index under the same name.
    """
    async with engine.connect() as raw:
        connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
        await connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            await connection.run_sync(Base.metadata.create_all)
            await add_columns_with_default(connection)
            await ensure_columns(connection)
            await replace_unique_indexes(connection)
            await ensure_indexes(connection)
            await backfill_card_status(connection)
            await remove_columns(connection)
            await ensure_artifact_search(connection)
        except BaseException:
            await connection.exec_driver_sql("ROLLBACK")
            raise
        await connection.exec_driver_sql("COMMIT")


async def backfill_card_status(connection: AsyncConnection) -> None:
    """Give every card an older release stored the status its type starts with.

    A card kept no status before ``card_status`` existed, so its column is null
    after the upgrade and a filter on status would never find it. Each type that
    carries a status is matched on the encoded ``card_type`` of either copy, and
    only rows still null are touched, so a rerun changes nothing and a card the
    user already moved along keeps its status.
    """
    backfilled = 0
    for card_type in CARD_STATUSES:
        starting = default_status(card_type)
        if starting is None:
            continue
        marker = f'"card_type":"{card_type.value}"'
        result = await connection.execute(
            sql_update(SessionArtifactRow)
            .where(
                SessionArtifactRow.card_status.is_(None),
                SessionArtifactRow.artifact_type == int(TYPE_TO_CODE[ArtifactType.CARD]),
                or_(
                    SessionArtifactRow.content_json.contains(marker),
                    SessionArtifactRow.draft_content_json.contains(marker),
                ),
            )
            .values(card_status=int(CARD_STATUS_TO_CODE[starting]))
            .execution_options(synchronize_session=False)
        )
        backfilled += result.rowcount
    if backfilled:
        logger.info("Backfilled card status for cards an older database stored; cards=%d", backfilled)


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

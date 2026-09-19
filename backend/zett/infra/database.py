"""Asynchronous SQLAlchemy transactions for application records.

Artifacts, assets, tags, providers, and key-value settings live in the
application database; Agent session history stays in the separate zett-agent
database. Both are asynchronous, so routes await one engine each instead of
hopping through a worker thread per DAO call.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex

from ..config import settings
from .models import Base

#: NullPool keeps every connection inside the loop that opened it, matching the
#: Agent session storage and allowing tests to swap paths per event loop.
engine = create_async_engine(
    URL.create("sqlite+aiosqlite", database=str(settings.database_path)),
    poolclass=NullPool,
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def ensure_indexes(connection: AsyncConnection) -> None:
    """Add indexes missing from databases created by an older application version."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            await connection.execute(CreateIndex(index, if_not_exists=True))


async def init_db() -> None:
    """Create the current schema; do not migrate retired application tables."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await ensure_indexes(connection)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """Commit successful operations and roll back failed ones."""
    async with session_factory() as session, session.begin():
        yield session

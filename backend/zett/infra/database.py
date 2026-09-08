"""SQLAlchemy transactions for Asset and Artifact records only."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ..config import settings
from .models import Base

engine = create_engine(f"sqlite:///{settings.database_path}", future=True)


def init_db() -> None:
    """Create the current schema; do not migrate retired application tables."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Generator[Session]:
    """Commit successful operations and roll back failed ones."""
    with Session(engine) as session, session.begin():
        yield session

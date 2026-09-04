import sqlite3
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ..config import settings
from .models import Base


def connect() -> sqlite3.Connection:
    """Open a low-level connection for legacy or SQLite-specific operations."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    return connection


engine = create_engine(f"sqlite:///{settings.database_path}", future=True)


def init_db() -> None:
    """Create all ORM-defined tables if they do not exist."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """Provide a SQLAlchemy session with commit and rollback semantics."""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def transaction():
    """Provide a low-level SQLite transaction for remaining adapters."""
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

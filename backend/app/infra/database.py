import sqlite3
from contextlib import contextmanager

from ..config import settings

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY, type TEXT NOT NULL DEFAULT 'note', title TEXT NOT NULL,
    content TEXT NOT NULL, raw_content TEXT, summary TEXT, source TEXT,
    status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    parent_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    description TEXT, color TEXT, created_at TEXT NOT NULL, UNIQUE(parent_id, name)
);
CREATE TABLE IF NOT EXISTS card_tags (
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    is_primary INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(card_id, tag_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(card_id UNINDEXED, title, content, summary, source);
CREATE TABLE IF NOT EXISTS ai_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1), provider TEXT NOT NULL, model TEXT NOT NULL,
    base_url TEXT, encrypted_api_key TEXT, temperature REAL NOT NULL DEFAULT 0.2,
    enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, provider TEXT NOT NULL,
    model TEXT NOT NULL, input_text TEXT NOT NULL, output_json TEXT, status TEXT NOT NULL,
    error_message TEXT, created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)


@contextmanager
def transaction():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

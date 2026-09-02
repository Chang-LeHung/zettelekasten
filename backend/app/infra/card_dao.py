import uuid
from datetime import UTC, datetime

from fastapi import HTTPException

from ..schemas import CardCreate, CardOut
from .database import transaction
from .list_options import CardListOptions
from .storage import Storage
from .tag_dao import to_dict as tag_to_dict


def _hydrate(connection, row) -> dict:
    result = dict(row)
    result["tag_ids"] = [
        r[0] for r in connection.execute("SELECT tag_id FROM card_tags WHERE card_id=?", (result["id"],))
    ]
    result["tags"] = [
        tag_to_dict(connection, tag)
        for tag in connection.execute(
            "SELECT t.* FROM tags t JOIN card_tags ct ON ct.tag_id=t.id WHERE ct.card_id=? ORDER BY t.name",
            (result["id"],),
        )
    ]
    return result


def _save(payload: CardCreate, card_id: str | None = None) -> dict:
    with transaction() as connection:
        timestamp = datetime.now(UTC).isoformat()
        card_id = card_id or str(uuid.uuid4())
        exists = connection.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone()
        if exists:
            connection.execute(
                "UPDATE cards SET type=?,title=?,content=?,raw_content=?,summary=?,source=?,updated_at=? WHERE id=?",
                (
                    payload.type,
                    payload.title,
                    payload.content,
                    payload.raw_content,
                    payload.summary,
                    payload.source,
                    timestamp,
                    card_id,
                ),
            )
            connection.execute("DELETE FROM card_tags WHERE card_id=?", (card_id,))
            connection.execute("DELETE FROM cards_fts WHERE card_id=?", (card_id,))
        else:
            connection.execute(
                "INSERT INTO cards(id,type,title,content,raw_content,summary,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    card_id,
                    payload.type,
                    payload.title,
                    payload.content,
                    payload.raw_content,
                    payload.summary,
                    payload.source,
                    timestamp,
                    timestamp,
                ),
            )
        for tag_id in set(payload.tag_ids):
            if connection.execute("SELECT 1 FROM tags WHERE id=?", (tag_id,)).fetchone():
                connection.execute("INSERT OR IGNORE INTO card_tags(card_id,tag_id) VALUES(?,?)", (card_id, tag_id))
        row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        connection.execute(
            "INSERT INTO cards_fts(card_id,title,content,summary,source) VALUES(?,?,?,?,?)",
            (card_id, row["title"], row["content"], row["summary"] or "", row["source"] or ""),
        )
        return _hydrate(connection, row)


def _get(card_id: str) -> dict:
    with transaction() as connection:
        row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Card not found")
        return _hydrate(connection, row)


def _search(options: CardListOptions | None = None) -> list[dict]:
    options = options or CardListOptions()
    query = options.query
    card_type = options.card_type
    tag_id = options.tag_id
    with transaction() as connection:
        params = []
        where = []
        source = "cards c"
        if query:
            source = "cards_fts JOIN cards c ON c.id=cards_fts.card_id"
            where.append("cards_fts MATCH ?")
            params.append(query.replace('"', " "))
        if card_type:
            where.append("c.type=?")
            params.append(card_type)
        if tag_id:
            where.append(
                "EXISTS (WITH RECURSIVE d(id) AS (SELECT ? UNION ALL SELECT t.id FROM tags t JOIN d ON t.parent_id=d.id) SELECT 1 FROM card_tags ct WHERE ct.card_id=c.id AND ct.tag_id IN d)"
            )
            params.append(tag_id)
        sql = (
            f"SELECT DISTINCT c.* FROM {source}"
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY c.updated_at DESC"
        )
        params.extend([options.limit, options.offset])
        sql += " LIMIT ? OFFSET ?"
        return [_hydrate(connection, row) for row in connection.execute(sql, params)]


def _delete(card_id: str) -> dict:
    with transaction() as connection:
        deleted = connection.execute("DELETE FROM cards WHERE id=?", (card_id,)).rowcount
        connection.execute("DELETE FROM cards_fts WHERE card_id=?", (card_id,))
        return {"ok": bool(deleted)}


class CardStorage(Storage[CardCreate, CardOut, str, CardListOptions]):
    """SQLite implementation of the generic card storage contract."""

    def create(self, entity: CardCreate) -> CardOut:
        return CardOut.model_validate(_save(entity))

    def get(self, entity_id: str) -> CardOut | None:
        return CardOut.model_validate(_get(entity_id))

    def update(self, entity_id: str, entity: CardCreate) -> CardOut:
        return CardOut.model_validate(_save(entity, entity_id))

    def delete(self, entity_id: str) -> bool:
        return bool(_delete(entity_id)["ok"])

    def list(self, options: CardListOptions | None = None) -> list[CardOut]:
        return [CardOut.model_validate(card) for card in _search(options)]


card_storage = CardStorage()

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException

from .database import db
from .tags import tag_out


def now():
    return datetime.now(UTC).isoformat()


def hydrate(conn, row):
    d = dict(row)
    d["tag_ids"] = [r[0] for r in conn.execute("SELECT tag_id FROM card_tags WHERE card_id=?", (d["id"],))]
    d["tags"] = [
        tag_out(conn, r)
        for r in conn.execute(
            "SELECT t.* FROM tags t JOIN card_tags ct ON ct.tag_id=t.id WHERE ct.card_id=? ORDER BY t.name", (d["id"],)
        )
    ]
    return d


def save_card(payload, card_id=None):
    with db() as conn:
        timestamp = now()
        card_id = card_id or str(uuid.uuid4())
        exists = conn.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone()
        if exists:
            conn.execute(
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
            conn.execute("DELETE FROM card_tags WHERE card_id=?", (card_id,))
            conn.execute("DELETE FROM cards_fts WHERE card_id=?", (card_id,))
        else:
            conn.execute(
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
            if conn.execute("SELECT 1 FROM tags WHERE id=?", (tag_id,)).fetchone():
                conn.execute("INSERT OR IGNORE INTO card_tags(card_id,tag_id) VALUES(?,?)", (card_id, tag_id))
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        conn.execute(
            "INSERT INTO cards_fts(card_id,title,content,summary,source) VALUES(?,?,?,?,?)",
            (card_id, row["title"], row["content"], row["summary"] or "", row["source"] or ""),
        )
        return hydrate(conn, row)


def get_card(card_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Card not found")
        return hydrate(conn, row)


def search_cards(q=None, type=None, tag_id=None):
    with db() as conn:
        params = []
        where = []
        if q:
            source = "cards_fts JOIN cards c ON c.id=cards_fts.card_id"
            where.append("cards_fts MATCH ?")
            params.append(q.replace('"', " "))
        else:
            source = "cards c"
        if type:
            where.append("c.type=?")
            params.append(type)
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
        return [hydrate(conn, r) for r in conn.execute(sql, params)]

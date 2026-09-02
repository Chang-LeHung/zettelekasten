from datetime import UTC, datetime

from fastapi import HTTPException

from ..schemas import TagCreate
from .database import transaction
from .list_options import TagListOptions
from .storage import Storage


def _path(connection, tag_id: int) -> str:
    row = connection.execute("SELECT name, parent_id FROM tags WHERE id=?", (tag_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Tag not found")
    names = [row["name"]]
    parent_id = row["parent_id"]
    while parent_id is not None:
        row = connection.execute("SELECT name, parent_id FROM tags WHERE id=?", (parent_id,)).fetchone()
        names.append(row["name"])
        parent_id = row["parent_id"]
    return "/".join(reversed(names))


def to_dict(connection, row) -> dict:
    result = dict(row)
    result["path"] = _path(connection, result["id"])
    result["card_count"] = connection.execute(
        "SELECT COUNT(*) FROM card_tags WHERE tag_id=?", (result["id"],)
    ).fetchone()[0]
    result["children"] = []
    return result


def _list_tags(options: TagListOptions | None = None) -> list[dict]:
    options = options or TagListOptions()
    with transaction() as connection:
        rows = [to_dict(connection, row) for row in connection.execute("SELECT * FROM tags ORDER BY name")]
        if not options.tree:
            return [row for row in rows if row["parent_id"] == options.parent_id]
        by_id = {row["id"]: row for row in rows}
        roots = []
        for row in rows:
            (by_id[row["parent_id"]]["children"] if row["parent_id"] else roots).append(row)
        return roots


def _create_tag(payload: TagCreate) -> dict:
    with transaction() as connection:
        if (
            payload.parent_id
            and not connection.execute("SELECT 1 FROM tags WHERE id=?", (payload.parent_id,)).fetchone()
        ):
            raise HTTPException(404, "Parent tag not found")
        try:
            cursor = connection.execute(
                "INSERT INTO tags(name,parent_id,description,color,created_at) VALUES(?,?,?,?,?)",
                (payload.name, payload.parent_id, payload.description, payload.color, datetime.now(UTC).isoformat()),
            )
        except Exception as exc:
            raise HTTPException(409, "A tag with this name already exists under the parent") from exc
        return to_dict(connection, connection.execute("SELECT * FROM tags WHERE id=?", (cursor.lastrowid,)).fetchone())


class TagStorage(Storage[TagCreate, int, TagListOptions]):
    """SQLite implementation of the generic tag storage contract."""

    def create(self, entity: TagCreate) -> dict:
        return _create_tag(entity)

    def get(self, entity_id: int) -> dict | None:
        with transaction() as connection:
            row = connection.execute("SELECT * FROM tags WHERE id=?", (entity_id,)).fetchone()
            return to_dict(connection, row) if row else None

    def update(self, entity_id: int, entity: TagCreate) -> dict:
        with transaction() as connection:
            if not connection.execute("SELECT 1 FROM tags WHERE id=?", (entity_id,)).fetchone():
                raise HTTPException(404, "Tag not found")
            connection.execute(
                "UPDATE tags SET name=?, parent_id=?, description=?, color=? WHERE id=?",
                (entity.name, entity.parent_id, entity.description, entity.color, entity_id),
            )
            return to_dict(connection, connection.execute("SELECT * FROM tags WHERE id=?", (entity_id,)).fetchone())

    def delete(self, entity_id: int) -> bool:
        with transaction() as connection:
            return bool(connection.execute("DELETE FROM tags WHERE id=?", (entity_id,)).rowcount)

    def list(self, options: TagListOptions | None = None) -> list[dict]:
        return _list_tags(options)


tag_storage = TagStorage()

from datetime import datetime, timezone
from fastapi import HTTPException

from .database import db


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(conn, tag_id: int) -> str:
    row = conn.execute(
        "SELECT name, parent_id FROM tags WHERE id=?", (tag_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Tag not found")
    names = [row["name"]]
    parent = row["parent_id"]
    while parent is not None:
        row = conn.execute(
            "SELECT name, parent_id FROM tags WHERE id=?", (parent,)
        ).fetchone()
        names.append(row["name"])
        parent = row["parent_id"]
    return "/".join(reversed(names))


def tag_out(conn, row):
    d = dict(row)
    d["path"] = _path(conn, d["id"])
    d["card_count"] = conn.execute(
        "SELECT COUNT(*) FROM card_tags WHERE tag_id=?", (d["id"],)
    ).fetchone()[0]
    d["children"] = []
    return d


def list_tags(tree=True):
    with db() as conn:
        rows = [
            tag_out(conn, r) for r in conn.execute("SELECT * FROM tags ORDER BY name")
        ]
        if not tree:
            return rows
        by_id = {r["id"]: r for r in rows}
        roots = []
        for r in rows:
            (by_id[r["parent_id"]]["children"] if r["parent_id"] else roots).append(r)
        return roots


def create_tag(payload):
    with db() as conn:
        if (
            payload.parent_id
            and not conn.execute(
                "SELECT 1 FROM tags WHERE id=?", (payload.parent_id,)
            ).fetchone()
        ):
            raise HTTPException(404, "Parent tag not found")
        try:
            cur = conn.execute(
                "INSERT INTO tags(name,parent_id,description,color,created_at) VALUES(?,?,?,?,?)",
                (
                    payload.name.strip(),
                    payload.parent_id,
                    payload.description,
                    payload.color,
                    now(),
                ),
            )
        except Exception as exc:
            raise HTTPException(
                409, "A tag with this name already exists under the parent"
            ) from exc
        return tag_out(
            conn,
            conn.execute("SELECT * FROM tags WHERE id=?", (cur.lastrowid,)).fetchone(),
        )

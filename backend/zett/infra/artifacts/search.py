"""SQLite FTS5 maintenance for full-text artifact search."""

import json
import re
from collections.abc import Iterable
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ...schemas import ArtifactContent

_CONTENT_ADAPTER = TypeAdapter(ArtifactContent)


def artifact_search_document(content: ArtifactContent | None, raw_content: str | None) -> tuple[str, str]:
    """Extract the weighted title and the complete searchable document body.

    The title is intentionally present in both FTS columns: ``title`` carries the
    higher BM25 weight, while ``body`` keeps the full document text available to
    normal content matching.

    ``content`` is the editable content the artifact shows, so an unpublished
    draft is searchable before its first save. An artifact without any content
    contributes only its original ``raw_content``.
    """
    if content is None:
        return "", raw_content or ""
    title = str(getattr(content, "title", "") or "").strip()
    payload = content.model_dump(exclude={"artifact_type", "project_path", "title"})
    body_parts = [title] if title else []
    body_parts.extend(_string_values(payload))
    if raw_content:
        body_parts.append(raw_content)
    return str(title), "\n".join(body_parts)


def build_fts_query(query: str) -> str | None:
    """Turn user text into a safe FTS5 prefix query."""
    tokens = [token for token in re.findall(r"\w+", query, flags=re.UNICODE) if len(token) >= 3]
    if not tokens:
        return None
    return " AND ".join(f'"{token}"' for token in tokens)


async def ensure_artifact_search(connection: AsyncConnection) -> None:
    """Create and backfill the FTS index for existing and future artifacts."""
    existing_sql = await connection.scalar(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'artifact_search'")
    )
    if existing_sql and "trigram" not in existing_sql:
        await connection.execute(text("DROP TABLE artifact_search"))
    await connection.execute(
        text(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS artifact_search USING fts5(
                artifact_id UNINDEXED,
                title,
                body,
                tokenize = 'trigram'
            )
            """
        )
    )
    existing = {
        row.artifact_id for row in (await connection.execute(text("SELECT artifact_id FROM artifact_search"))).all()
    }
    rows = (
        await connection.execute(
            text("SELECT id, content_json, draft_content_json, raw_content FROM session_artifacts")
        )
    ).all()
    for row in rows:
        if row.id in existing:
            continue
        content = _stored_content(row.content_json) or _stored_content(row.draft_content_json)
        title, body = artifact_search_document(content, row.raw_content)
        await _insert(connection, row.id, title, body)


def _stored_content(value: str | None) -> ArtifactContent | None:
    """Decode one stored content column, tolerating an absent or unreadable value."""
    if not value:
        return None
    try:
        return _CONTENT_ADAPTER.validate_python(json.loads(value))
    except (TypeError, ValueError):
        return None


async def upsert_artifact_search(
    session: AsyncSession,
    *,
    artifact_id: str,
    content: ArtifactContent,
    raw_content: str | None,
) -> None:
    """Replace one artifact document inside the FTS index."""
    await delete_artifact_search(session, artifact_id)
    title, body = artifact_search_document(content, raw_content)
    await _insert(session, artifact_id, title, body)


async def delete_artifact_search(session: AsyncSession, artifact_id: str) -> None:
    """Remove one artifact from the FTS index."""
    await session.execute(
        text("DELETE FROM artifact_search WHERE artifact_id = :artifact_id"),
        {"artifact_id": artifact_id},
    )


async def delete_artifacts_search(session: AsyncSession, artifact_ids: Iterable[str]) -> None:
    """Remove a batch of artifact documents from the FTS index."""
    values = tuple(dict.fromkeys(artifact_ids))
    if not values:
        return
    await session.execute(
        text("DELETE FROM artifact_search WHERE artifact_id IN :artifact_ids").bindparams(
            bindparam("artifact_ids", expanding=True)
        ),
        {"artifact_ids": values},
    )


async def _insert(
    executor: AsyncConnection | AsyncSession,
    artifact_id: str,
    title: str,
    body: str,
) -> None:
    await executor.execute(
        text("INSERT INTO artifact_search (artifact_id, title, body) VALUES (:artifact_id, :title, :body)"),
        {"artifact_id": artifact_id, "title": title, "body": body},
    )


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list | tuple):
        return [item for child in value for item in _string_values(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _string_values(child)]
    return []

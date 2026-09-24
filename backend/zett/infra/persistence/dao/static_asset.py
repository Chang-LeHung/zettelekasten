"""SQLite and filesystem storage for session-independent uploaded files."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from zett_agent import new_uuid7

from ...._compat import UTC
from ....application.files.object_store import static_asset_key
from ....schemas import StaticAssetCreate, StaticAssetEntity, StaticAssetListOptions
from ...files.object_store import get_object_store
from ..database import session_scope
from ..storage import AsyncStorage
from ..tables import StaticAssetRow


def _safe_suffix(name: str) -> str:
    """Keep a short extension without trusting the user-provided filename."""
    suffix = Path(name).suffix.lower()[:16]
    return suffix if re.fullmatch(r"\.[a-z0-9]+", suffix) else ""


def _asset_out(model: StaticAssetRow) -> StaticAssetEntity:
    """Convert one persisted row into its public typed representation."""
    object_store = get_object_store()
    return StaticAssetEntity(
        id=model.id,
        name=model.name,
        mime_type=model.mime_type,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        storage_path=model.storage_path,
        content_url=object_store.url(model.storage_path),
        metadata=json.loads(model.metadata_value),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class StaticAssetStorage(AsyncStorage[StaticAssetCreate, StaticAssetEntity, str, StaticAssetListOptions]):
    """Persist global uploaded files under one static directory."""

    async def create(self, entity: StaticAssetCreate) -> StaticAssetEntity:
        """Store one uploaded file and its typed metadata."""
        asset_id = new_uuid7()
        now = datetime.now(UTC)
        key = static_asset_key(asset_id, _safe_suffix(entity.name))
        object_store = get_object_store()
        stored = await object_store.write(key, entity.content)
        try:
            async with session_scope() as session:
                model = StaticAssetRow(
                    id=asset_id,
                    name=entity.name,
                    mime_type=entity.mime_type,
                    size_bytes=len(entity.content),
                    sha256=hashlib.sha256(entity.content).hexdigest(),
                    storage_path=str(stored.key),
                    metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                await session.flush()
                return _asset_out(model)
        except Exception:
            await object_store.delete(stored.key)
            raise

    async def get(self, entity_id: str) -> StaticAssetEntity | None:
        async with session_scope() as session:
            model = await session.get(StaticAssetRow, entity_id)
            return _asset_out(model) if model is not None else None

    async def update(self, entity_id: str, entity: StaticAssetCreate) -> StaticAssetEntity:
        """Replace file content and editable metadata while retaining identity."""
        replacement_key: str | None = None
        old_storage_path: str | None = None
        object_store = get_object_store()
        try:
            async with session_scope() as session:
                model = await session.get(StaticAssetRow, entity_id)
                if model is None:
                    raise KeyError(f"Static asset not found: {entity_id}")
                old_storage_path = model.storage_path
                revision = new_uuid7()
                key = static_asset_key(f"{entity_id}-{revision}", _safe_suffix(entity.name))
                stored = await object_store.write(key, entity.content)
                replacement_key = str(stored.key)
                model.name = entity.name
                model.mime_type = entity.mime_type
                model.size_bytes = len(entity.content)
                model.sha256 = hashlib.sha256(entity.content).hexdigest()
                model.storage_path = replacement_key
                model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
                model.updated_at = datetime.now(UTC)
                await session.flush()
                result = _asset_out(model)
        except Exception:
            if replacement_key is not None:
                await object_store.delete(replacement_key)
            raise
        if old_storage_path is not None and old_storage_path != replacement_key:
            await object_store.delete(old_storage_path)
        return result

    async def delete(self, entity_id: str) -> bool:
        """Delete metadata first, then explicitly remove the owned file."""
        storage_path: str | None = None
        async with session_scope() as session:
            model = await session.get(StaticAssetRow, entity_id)
            if model is None:
                return False
            storage_path = model.storage_path
            await session.delete(model)
        if storage_path is not None:
            await get_object_store().delete(storage_path)
        return True

    async def list(self, options: StaticAssetListOptions | None = None) -> list[StaticAssetEntity]:
        options = options or StaticAssetListOptions()
        async with session_scope() as session:
            statement = select(StaticAssetRow)
            if options.query:
                statement = statement.where(StaticAssetRow.name.ilike(f"%{options.query}%"))
            statement = (
                statement.order_by(StaticAssetRow.created_at.desc(), StaticAssetRow.id.desc())
                .limit(options.limit)
                .offset(options.offset)
            )
            return [_asset_out(model) for model in await session.scalars(statement)]

    async def content_path(self, entity_id: str) -> Path | None:
        """Resolve one stored file after confirming its metadata exists."""
        async with session_scope() as session:
            model = await session.get(StaticAssetRow, entity_id)
            if model is None:
                return None
            path = get_object_store().resolve(model.storage_path)
            return path if path.is_file() else None


static_asset_storage = StaticAssetStorage()

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from zett_agent import new_uuid7

from ...application.object_store import session_asset_key
from ...schemas import SessionAssetCreate, SessionAssetEntity, SessionAssetListOptions, SessionAssetType
from ..database import session_scope
from ..files.object_store import get_object_store
from ..storage import AsyncStorage
from ..tables import SessionAssetRow


class AssetTypeCode(IntEnum):
    """Numeric persistence representation for finite session asset types."""

    TEXT = 1
    IMAGE = 2
    LINK = 3
    FILE = 4


ASSET_TO_CODE = {
    SessionAssetType.TEXT: AssetTypeCode.TEXT,
    SessionAssetType.IMAGE: AssetTypeCode.IMAGE,
    SessionAssetType.LINK: AssetTypeCode.LINK,
    SessionAssetType.FILE: AssetTypeCode.FILE,
}
CODE_TO_ASSET = {int(code): asset_type for asset_type, code in ASSET_TO_CODE.items()}
FILE_ASSET_TYPES = (SessionAssetType.IMAGE, SessionAssetType.FILE)


def _asset_out(model: SessionAssetRow) -> SessionAssetEntity:
    """Convert one ORM row into the typed public asset representation."""
    asset_type = CODE_TO_ASSET[model.asset_type]
    object_store = get_object_store()
    content_url = (
        object_store.url(model.storage_path)
        if model.storage_path
        else object_store.url(model.source_path)
        if model.source_path
        else None
    )
    return SessionAssetEntity(
        id=model.id,
        session_id=model.session_id,
        asset_type=asset_type,
        name=model.name,
        mime_type=model.mime_type,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        text_content=model.text_content,
        source_url=model.source_url,
        storage_path=model.storage_path,
        source_path=model.source_path,
        content_url=content_url,
        metadata=json.loads(model.metadata_value),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _safe_suffix(name: str) -> str:
    """Keep a short extension for content disposition without trusting user paths."""
    suffix = Path(name).suffix.lower()[:16]
    return suffix if re.fullmatch(r"\.[a-z0-9]+", suffix) else ""


def _validate_payload(entity: SessionAssetCreate) -> None:
    """Validate content consistently before any database or filesystem mutation."""
    match entity.asset_type:
        case SessionAssetType.IMAGE | SessionAssetType.FILE:
            if entity.content is None and entity.source_path is None:
                raise ValueError("Binary asset content or a referenced object path is required")
        case SessionAssetType.TEXT:
            if entity.text_content is None:
                raise ValueError("Text asset content is required")
        case SessionAssetType.LINK:
            if bool(entity.source_url) == bool(entity.source_path):
                raise ValueError("Link asset requires exactly one external URL or referenced object path")


class SessionAssetStorage(AsyncStorage[SessionAssetCreate, SessionAssetEntity, str, SessionAssetListOptions]):
    """Persist session asset metadata in SQLite and binary payloads on local disk."""

    async def create(self, entity: SessionAssetCreate) -> SessionAssetEntity:
        """Store one asset after confirming its Agent session exists."""
        _validate_payload(entity)
        from ..agent.runtime import get_agent_runtime_storage

        if await get_agent_runtime_storage().get_session(entity.session_id) is None:
            raise KeyError(f"Agent session not found: {entity.session_id}")
        asset_id = new_uuid7()
        now = datetime.now(UTC)
        object_store = get_object_store()
        storage_path: str | None = None
        written_key: str | None = None
        if entity.asset_type in FILE_ASSET_TYPES and entity.content is not None:
            key = session_asset_key(entity.session_id, asset_id, _safe_suffix(entity.name))
            stored = await object_store.write(key, entity.content)
            storage_path = str(stored.key)
            written_key = storage_path
        elif entity.asset_type == SessionAssetType.TEXT and entity.text_content is None:
            raise ValueError("Text asset content is required")

        payload = entity.content or (entity.text_content or entity.source_url or entity.source_path or "").encode()
        try:
            async with session_scope() as session:
                model = SessionAssetRow(
                    id=asset_id,
                    session_id=entity.session_id,
                    asset_type=int(ASSET_TO_CODE[entity.asset_type]),
                    name=entity.name,
                    mime_type=entity.mime_type,
                    size_bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    storage_path=storage_path,
                    text_content=entity.text_content,
                    source_url=entity.source_url,
                    source_path=entity.source_path,
                    metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                await session.flush()
                result = _asset_out(model)
            return result
        except Exception:
            if written_key is not None:
                await object_store.delete(written_key)
            raise

    async def get(self, entity_id: str) -> SessionAssetEntity | None:
        async with session_scope() as session:
            model = await session.get(SessionAssetRow, entity_id)
            return _asset_out(model) if model else None

    async def update(self, entity_id: str, entity: SessionAssetCreate) -> SessionAssetEntity:
        _validate_payload(entity)
        replacement_key: str | None = None
        old_storage_path: str | None = None
        object_store = get_object_store()
        try:
            async with session_scope() as session:
                model = await session.get(SessionAssetRow, entity_id)
                if model is None or model.session_id != entity.session_id:
                    raise KeyError(f"Session asset not found: {entity_id}")
                old_storage_path = model.storage_path
                storage_path: str | None = None
                if entity.asset_type in FILE_ASSET_TYPES and entity.content is not None:
                    revision = new_uuid7()
                    key = session_asset_key(
                        entity.session_id,
                        f"{entity_id}-{revision}",
                        _safe_suffix(entity.name),
                    )
                    stored = await object_store.write(key, entity.content)
                    storage_path = str(stored.key)
                    replacement_key = storage_path
                payload = (
                    entity.content or (entity.text_content or entity.source_url or entity.source_path or "").encode()
                )
                model.asset_type = int(ASSET_TO_CODE[entity.asset_type])
                model.name = entity.name
                model.mime_type = entity.mime_type
                model.size_bytes = len(payload)
                model.sha256 = hashlib.sha256(payload).hexdigest()
                model.storage_path = storage_path
                model.text_content = entity.text_content
                model.source_url = entity.source_url
                model.source_path = entity.source_path
                model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
                model.updated_at = datetime.now(UTC)
                await session.flush()
                result = _asset_out(model)
        except Exception:
            if replacement_key is not None:
                await object_store.delete(replacement_key)
            raise
        if old_storage_path is not None and old_storage_path != storage_path:
            await object_store.delete(old_storage_path)
        return result

    async def rename(self, session_id: str, entity_id: str, name: str) -> SessionAssetEntity:
        """Change display metadata only; never rewrite bytes or their UUID path."""
        async with session_scope() as session:
            model = await session.get(SessionAssetRow, entity_id)
            if model is None or model.session_id != session_id:
                raise KeyError(f"Session asset not found: {entity_id}")
            model.name = name
            model.updated_at = datetime.now(UTC)
            await session.flush()
            return _asset_out(model)

    async def delete(self, entity_id: str) -> bool:
        storage_path: str | None = None
        async with session_scope() as session:
            model = await session.get(SessionAssetRow, entity_id)
            if model is None:
                return False
            storage_path = model.storage_path
            await session.delete(model)
        if storage_path is not None:
            await get_object_store().delete(storage_path)
        return True

    async def list(self, options: SessionAssetListOptions | None = None) -> list[SessionAssetEntity]:
        options = options or SessionAssetListOptions()
        async with session_scope() as session:
            statement = select(SessionAssetRow)
            if options.session_id:
                statement = statement.where(SessionAssetRow.session_id == options.session_id)
            if options.query:
                statement = statement.where(SessionAssetRow.name.ilike(f"%{options.query}%"))
            if options.asset_types:
                codes = [int(ASSET_TO_CODE[SessionAssetType(value)]) for value in options.asset_types]
                statement = statement.where(SessionAssetRow.asset_type.in_(codes))
            statement = (
                statement.order_by(SessionAssetRow.created_at, SessionAssetRow.id)
                .limit(options.limit)
                .offset(options.offset)
            )
            return [_asset_out(model) for model in await session.scalars(statement)]

    async def get_for_session(self, session_id: str, asset_id: str) -> SessionAssetEntity | None:
        """Read an asset only when it belongs to the requested session."""
        asset = await self.get(asset_id)
        return asset if asset and asset.session_id == session_id else None

    async def content_path(self, session_id: str, asset_id: str) -> Path | None:
        """Resolve a stored binary path after verifying session ownership."""
        async with session_scope() as session:
            model = await session.get(SessionAssetRow, asset_id)
            if model is None or model.session_id != session_id or not model.storage_path:
                return None
            path = get_object_store().resolve(model.storage_path)
            return path if path.is_file() else None

    async def delete_session(self, session_id: str) -> None:
        """Explicitly remove all metadata and files owned by one session."""
        async with session_scope() as session:
            storage_paths = tuple(
                await session.scalars(
                    select(SessionAssetRow.storage_path).where(
                        SessionAssetRow.session_id == session_id,
                        SessionAssetRow.storage_path.is_not(None),
                    )
                )
            )
            await session.execute(sql_delete(SessionAssetRow).where(SessionAssetRow.session_id == session_id))
        object_store = get_object_store()
        for storage_path in storage_paths:
            if storage_path is not None:
                await object_store.delete(storage_path)


session_asset_storage = SessionAssetStorage()

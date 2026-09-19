"""SQLite and filesystem storage for session-independent uploaded files."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from zett_agent import new_uuid7

from ...config import settings
from ...models import StaticAssetListOptions
from ...schemas import StaticAssetCreate, StaticAssetOut
from ..database import session_scope
from ..models import StaticAssetModel
from ..storage import AsyncStorage


def _safe_suffix(name: str) -> str:
    """Keep a short extension without trusting the user-provided filename."""
    suffix = Path(name).suffix.lower()[:16]
    return suffix if re.fullmatch(r"\.[a-z0-9]+", suffix) else ""


def _asset_out(model: StaticAssetModel) -> StaticAssetOut:
    """Convert one persisted row into its public typed representation."""
    return StaticAssetOut(
        id=model.id,
        name=model.name,
        mime_type=model.mime_type,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        content_url=f"/api/assets/{model.id}/content",
        metadata=json.loads(model.metadata_value),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class StaticAssetStorage(AsyncStorage[StaticAssetCreate, StaticAssetOut, str, StaticAssetListOptions]):
    """Persist global uploaded files under one static directory."""

    async def create(self, entity: StaticAssetCreate) -> StaticAssetOut:
        """Store one uploaded file and its typed metadata."""
        asset_id = new_uuid7()
        now = datetime.now(UTC)
        storage_name = f"{asset_id}{_safe_suffix(entity.name)}"
        written_path = self._directory() / storage_name
        written_path.write_bytes(entity.content)
        try:
            async with session_scope() as session:
                model = StaticAssetModel(
                    id=asset_id,
                    name=entity.name,
                    mime_type=entity.mime_type,
                    size_bytes=len(entity.content),
                    sha256=hashlib.sha256(entity.content).hexdigest(),
                    storage_name=storage_name,
                    metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                await session.flush()
                return _asset_out(model)
        except Exception:
            written_path.unlink(missing_ok=True)
            raise

    async def get(self, entity_id: str) -> StaticAssetOut | None:
        async with session_scope() as session:
            model = await session.get(StaticAssetModel, entity_id)
            return _asset_out(model) if model is not None else None

    async def update(self, entity_id: str, entity: StaticAssetCreate) -> StaticAssetOut:
        """Replace file content and editable metadata while retaining identity."""
        replacement_path: Path | None = None
        old_path: Path | None = None
        try:
            async with session_scope() as session:
                model = await session.get(StaticAssetModel, entity_id)
                if model is None:
                    raise KeyError(f"Static asset not found: {entity_id}")
                old_path = self._directory() / model.storage_name
                revision = new_uuid7()
                storage_name = f"{entity_id}-{revision}{_safe_suffix(entity.name)}"
                replacement_path = self._directory() / storage_name
                replacement_path.write_bytes(entity.content)
                model.name = entity.name
                model.mime_type = entity.mime_type
                model.size_bytes = len(entity.content)
                model.sha256 = hashlib.sha256(entity.content).hexdigest()
                model.storage_name = storage_name
                model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
                model.updated_at = datetime.now(UTC)
                await session.flush()
                result = _asset_out(model)
        except Exception:
            if replacement_path is not None:
                replacement_path.unlink(missing_ok=True)
            raise
        if old_path is not None and old_path != replacement_path:
            old_path.unlink(missing_ok=True)
        return result

    async def delete(self, entity_id: str) -> bool:
        """Delete metadata first, then explicitly remove the owned file."""
        stored_path: Path | None = None
        async with session_scope() as session:
            model = await session.get(StaticAssetModel, entity_id)
            if model is None:
                return False
            stored_path = self._directory() / model.storage_name
            await session.delete(model)
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        return True

    async def list(self, options: StaticAssetListOptions | None = None) -> list[StaticAssetOut]:
        options = options or StaticAssetListOptions()
        async with session_scope() as session:
            statement = select(StaticAssetModel)
            if options.query:
                statement = statement.where(StaticAssetModel.name.ilike(f"%{options.query}%"))
            statement = (
                statement.order_by(StaticAssetModel.created_at.desc(), StaticAssetModel.id.desc())
                .limit(options.limit)
                .offset(options.offset)
            )
            return [_asset_out(model) for model in await session.scalars(statement)]

    async def content_path(self, entity_id: str) -> Path | None:
        """Resolve one stored file after confirming its metadata exists."""
        async with session_scope() as session:
            model = await session.get(StaticAssetModel, entity_id)
            if model is None:
                return None
            path = self._directory() / model.storage_name
            return path if path.is_file() else None

    @staticmethod
    def _directory() -> Path:
        directory = settings.asset_directory / "static"
        directory.mkdir(parents=True, exist_ok=True)
        return directory


static_asset_storage = StaticAssetStorage()

"""Use-case orchestration for files shared outside Agent sessions."""

from __future__ import annotations

from pathlib import Path

from ...infra.persistence.dao import session_asset_storage, static_asset_storage
from ...schemas import StaticAssetCreate, StaticAssetEntity, StaticAssetListOptions
from ..runtime.settings import runtime_settings_service


class StaticAssetService:
    """List, upload, delete, and resolve global static assets."""

    async def list(self, options: StaticAssetListOptions | None = None) -> list[StaticAssetEntity]:
        return await static_asset_storage.list(options)

    async def get(self, asset_id: str) -> StaticAssetEntity | None:
        return await static_asset_storage.get(asset_id)

    async def upload(self, *, name: str, mime_type: str | None, content: bytes) -> StaticAssetEntity:
        """Persist one uploaded file after applying the runtime size limit."""
        runtime_settings = await runtime_settings_service.get()
        if len(content) > runtime_settings.max_asset_size_bytes:
            raise ValueError("Asset exceeds the configured size limit")
        return await static_asset_storage.create(StaticAssetCreate(name=name, mime_type=mime_type, content=content))

    async def delete(self, asset_id: str) -> bool:
        asset = await static_asset_storage.get(asset_id)
        if asset is None:
            return False
        if await session_asset_storage.references_static_asset(asset.id, asset.storage_path):
            raise ValueError("Static asset is still referenced by session assets")
        return await static_asset_storage.delete(asset_id)

    async def content_path(self, asset_id: str) -> Path | None:
        return await static_asset_storage.content_path(asset_id)

    async def max_upload_size(self) -> int:
        """Return the current application-level upload limit."""
        return (await runtime_settings_service.get()).max_asset_size_bytes


static_asset_service = StaticAssetService()

"""Asynchronous endpoints for session-owned text, link, image, and file assets."""

from fastapi import APIRouter, HTTPException, Query, Request, status

from ....infra.persistence.dao import session_asset_storage, session_storage
from ....schemas import SessionAssetCreate, SessionAssetEntity, SessionAssetListOptions, SessionAssetType
from ...assets.asset_names import AssetRenameIn, rename_asset
from ...assets.static_assets import static_asset_service
from ...runtime.settings import runtime_settings_service
from ..schemas import DeleteResponse, LinkAssetIn, TextAssetIn

router = APIRouter(prefix="/agent/{session_id}/assets", tags=["assets"])


async def _require_session(session_id: str) -> None:
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")


@router.get("", response_model=list[SessionAssetEntity])
async def list_assets(
    session_id: str,
    query: str | None = None,
    asset_types: list[SessionAssetType] = Query(default=[]),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SessionAssetEntity]:
    """List one session's assets with optional type and name filters."""
    await _require_session(session_id)
    options = SessionAssetListOptions(
        session_id=session_id,
        query=query,
        asset_types=tuple(item.value for item in asset_types),
        limit=limit,
        offset=offset,
    )
    return await session_asset_storage.list(options)


@router.get("/{asset_id}", response_model=SessionAssetEntity)
async def get_asset(session_id: str, asset_id: str) -> SessionAssetEntity:
    """Read asset metadata only within its owning session."""
    asset = await session_asset_storage.get_for_session(session_id, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


@router.post("/text", response_model=SessionAssetEntity, status_code=status.HTTP_201_CREATED)
async def create_text_asset(session_id: str, payload: TextAssetIn) -> SessionAssetEntity:
    """Attach inline text to a session."""
    await _require_session(session_id)
    entity = SessionAssetCreate(
        session_id=session_id,
        asset_type=SessionAssetType.TEXT,
        name=payload.name,
        mime_type=payload.mime_type,
        text_content=payload.content,
        metadata=payload.metadata,
    )
    return await session_asset_storage.create(entity)


@router.post("/link", response_model=SessionAssetEntity, status_code=status.HTTP_201_CREATED)
async def create_link_asset(session_id: str, payload: LinkAssetIn) -> SessionAssetEntity:
    """Attach an external URL without downloading its content."""
    await _require_session(session_id)
    entity = SessionAssetCreate(
        session_id=session_id,
        asset_type=SessionAssetType.LINK,
        name=payload.name,
        source_url=payload.url,
        metadata=payload.metadata,
    )
    return await session_asset_storage.create(entity)


@router.post("/import/static/{static_asset_id}", response_model=SessionAssetEntity, status_code=status.HTTP_201_CREATED)
async def import_static_asset(session_id: str, static_asset_id: str) -> SessionAssetEntity:
    """Reference one global static asset by object key without copying its file."""
    await _require_session(session_id)
    static_asset = await static_asset_service.get(static_asset_id)
    if static_asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Static asset not found")
    entity = SessionAssetCreate(
        session_id=session_id,
        asset_type=SessionAssetType.LINK,
        name=static_asset.name,
        mime_type=static_asset.mime_type,
        source_path=static_asset.storage_path,
        metadata={
            "import_mode": "object",
            "static_asset_id": static_asset.id,
            "static_asset_size_bytes": static_asset.size_bytes,
            "static_asset_sha256": static_asset.sha256,
        },
    )
    return await session_asset_storage.create(entity)


@router.post("/upload", response_model=SessionAssetEntity, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    session_id: str, request: Request, name: str = Query(min_length=1, max_length=500)
) -> SessionAssetEntity:
    """Store a raw request body as an image or generic file asset."""
    await _require_session(session_id)
    runtime_settings = await runtime_settings_service.get()
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > runtime_settings.max_asset_size_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Asset exceeds the configured size limit")
    mime_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    asset_type = SessionAssetType.IMAGE if mime_type.startswith("image/") else SessionAssetType.FILE
    entity = SessionAssetCreate(
        session_id=session_id,
        asset_type=asset_type,
        name=name,
        mime_type=mime_type,
        content=bytes(content),
    )
    try:
        return await session_asset_storage.create(entity)
    except ValueError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error


@router.delete("/{asset_id}", response_model=DeleteResponse)
async def delete_asset(session_id: str, asset_id: str) -> DeleteResponse:
    """Delete an asset only when it belongs to the path session."""
    asset = await session_asset_storage.get_for_session(session_id, asset_id)
    if asset is None:
        return DeleteResponse(ok=False)
    return DeleteResponse(ok=await session_asset_storage.delete(asset_id))


@router.patch("/{asset_id}/name", response_model=SessionAssetEntity)
async def rename_asset_route(session_id: str, asset_id: str, payload: AssetRenameIn) -> SessionAssetEntity:
    """Rename the display label without changing stored file names or URLs."""
    try:
        return await rename_asset(session_id, asset_id, payload)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found") from error

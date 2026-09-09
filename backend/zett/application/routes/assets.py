"""Asynchronous endpoints for session-owned text, link, image, and file assets."""

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from ...config import settings
from ...infra.dao import session_asset_storage, session_storage
from ...models import SessionAssetListOptions
from ...schemas import SessionAssetCreate, SessionAssetOut, SessionAssetType
from ..dependencies import run_sync
from ..schemas import DeleteResponse, LinkAssetIn, TextAssetIn

router = APIRouter(prefix="/agent/{session_id}/assets", tags=["assets"])


async def _require_session(session_id: str) -> None:
    if await run_sync(session_storage.get, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")


@router.get("", response_model=list[SessionAssetOut])
async def list_assets(
    session_id: str,
    query: str | None = None,
    asset_types: list[SessionAssetType] = Query(default=[]),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SessionAssetOut]:
    """List one session's assets with optional type and name filters."""
    await _require_session(session_id)
    options = SessionAssetListOptions(
        session_id=session_id,
        query=query,
        asset_types=tuple(item.value for item in asset_types),
        limit=limit,
        offset=offset,
    )
    return await run_sync(session_asset_storage.list, options)


@router.get("/{asset_id}", response_model=SessionAssetOut)
async def get_asset(session_id: str, asset_id: str) -> SessionAssetOut:
    """Read asset metadata only within its owning session."""
    asset = await run_sync(session_asset_storage.get_for_session, session_id, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


@router.post("/text", response_model=SessionAssetOut, status_code=status.HTTP_201_CREATED)
async def create_text_asset(session_id: str, payload: TextAssetIn) -> SessionAssetOut:
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
    return await run_sync(session_asset_storage.create, entity)


@router.post("/link", response_model=SessionAssetOut, status_code=status.HTTP_201_CREATED)
async def create_link_asset(session_id: str, payload: LinkAssetIn) -> SessionAssetOut:
    """Attach an external URL without downloading its content."""
    await _require_session(session_id)
    entity = SessionAssetCreate(
        session_id=session_id,
        asset_type=SessionAssetType.LINK,
        name=payload.name,
        source_url=payload.url,
        metadata=payload.metadata,
    )
    return await run_sync(session_asset_storage.create, entity)


@router.post("/upload", response_model=SessionAssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    session_id: str, request: Request, name: str = Query(min_length=1, max_length=500)
) -> SessionAssetOut:
    """Store a raw request body as an image or generic file asset."""
    await _require_session(session_id)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > settings.max_asset_size_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Asset exceeds the configured size limit")
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
        return await run_sync(session_asset_storage.create, entity)
    except ValueError as error:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(error)) from error


@router.get("/{asset_id}/content", response_class=FileResponse)
async def get_asset_content(session_id: str, asset_id: str) -> FileResponse:
    """Serve binary content only after verifying session ownership."""
    asset = await run_sync(session_asset_storage.get_for_session, session_id, asset_id)
    path = await run_sync(session_asset_storage.content_path, session_id, asset_id)
    if asset is None or path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset content not found")
    return FileResponse(path, media_type=asset.mime_type, filename=asset.name)


@router.delete("/{asset_id}", response_model=DeleteResponse)
async def delete_asset(session_id: str, asset_id: str) -> DeleteResponse:
    """Delete an asset only when it belongs to the path session."""
    asset = await run_sync(session_asset_storage.get_for_session, session_id, asset_id)
    if asset is None:
        return DeleteResponse(ok=False)
    return DeleteResponse(ok=await run_sync(session_asset_storage.delete, asset_id))

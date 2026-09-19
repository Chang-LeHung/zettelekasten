"""HTTP endpoints for files that are shared across Agent sessions."""

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from ...models import StaticAssetListOptions
from ...schemas import StaticAssetOut
from ..schemas import DeleteResponse
from ..static_assets import static_asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[StaticAssetOut])
async def list_assets(
    query: str | None = None,
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[StaticAssetOut]:
    """List global uploaded files, newest first."""
    return await static_asset_service.list(StaticAssetListOptions(query=query, limit=limit, offset=offset))


@router.post("/upload", response_model=StaticAssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    request: Request,
    name: str = Query(min_length=1, max_length=500),
) -> StaticAssetOut:
    """Upload one file without attaching it to a conversation."""
    max_size = await static_asset_service.max_upload_size()
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > max_size:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Asset exceeds the configured size limit")
    mime_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    try:
        return await static_asset_service.upload(name=name, mime_type=mime_type, content=bytes(content))
    except ValueError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error


@router.get("/{asset_id}", response_model=StaticAssetOut)
async def get_asset(asset_id: str) -> StaticAssetOut:
    """Read one global asset's metadata."""
    asset = await static_asset_service.get(asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


@router.get("/{asset_id}/content", response_class=FileResponse)
async def get_asset_content(asset_id: str) -> FileResponse:
    """Preview images and PDFs inline and download other global files."""
    asset = await static_asset_service.get(asset_id)
    path = await static_asset_service.content_path(asset_id)
    if asset is None or path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset content not found")
    inline = bool(asset.mime_type and (asset.mime_type.startswith("image/") or asset.mime_type == "application/pdf"))
    headers = {"X-Content-Type-Options": "nosniff"}
    if inline:
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=asset.name,
        content_disposition_type="inline" if inline else "attachment",
        headers=headers,
    )


@router.delete("/{asset_id}", response_model=DeleteResponse)
async def delete_asset(asset_id: str) -> DeleteResponse:
    """Delete one global asset and its owned file."""
    return DeleteResponse(ok=await static_asset_service.delete(asset_id))

"""HTTP endpoints for files that are shared across Agent sessions."""

from fastapi import APIRouter, HTTPException, Query, Request, status

from ....infra.log import get_logger, log_preview
from ....schemas import StaticAssetEntity, StaticAssetListOptions
from ...assets.static_assets import static_asset_service
from ...tags.tagging import tag_service
from ..schemas import DeleteResponse

router = APIRouter(prefix="/assets", tags=["assets"])

logger = get_logger(__name__)


@router.get("", response_model=list[StaticAssetEntity])
async def list_assets(
    query: str | None = None,
    tag_ids: list[str] = Query(default=[]),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[StaticAssetEntity]:
    """List global uploaded files, newest first.

    ``tag_ids`` narrows the list to the files a collection carries, expanding
    each id to its descendants exactly like the artifact library does, so
    clicking a parent collection shows the files tagged anywhere below it.
    """
    try:
        expanded_tag_ids = await tag_service.subtree_ids(tag_ids) if tag_ids else ()
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    return await static_asset_service.list(
        StaticAssetListOptions(query=query, tag_ids=expanded_tag_ids, limit=limit, offset=offset)
    )


@router.post("/upload", response_model=StaticAssetEntity, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    request: Request,
    name: str = Query(min_length=1, max_length=500),
) -> StaticAssetEntity:
    """Upload one file without attaching it to a conversation."""
    if not name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Asset name cannot be blank")
    max_size = await static_asset_service.max_upload_size()
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > max_size:
            logger.warning(
                "Static asset upload rejected; name=%r bytes=%d limit_bytes=%d",
                log_preview(name),
                len(content),
                max_size,
            )
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Asset exceeds the configured size limit")
    mime_type = request.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    if len(mime_type) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "MIME type is too long")
    try:
        stored = await static_asset_service.upload(name=name, mime_type=mime_type, content=bytes(content))
    except ValueError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error
    logger.info(
        "Static asset uploaded; asset_id=%s name=%r mime_type=%s bytes=%d",
        stored.id,
        log_preview(stored.name),
        stored.mime_type,
        stored.size_bytes,
    )
    return stored


@router.get("/{asset_id}", response_model=StaticAssetEntity)
async def get_asset(asset_id: str) -> StaticAssetEntity:
    """Read one global asset's metadata."""
    asset = await static_asset_service.get(asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


@router.delete("/{asset_id}", response_model=DeleteResponse)
async def delete_asset(asset_id: str) -> DeleteResponse:
    """Delete one global asset and its owned file."""
    try:
        return DeleteResponse(ok=await static_asset_service.delete(asset_id))
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

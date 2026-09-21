"""The single HTTP surface for every object stored below storage_root."""

import mimetypes

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from ...infra.files.object_store import get_object_store
from ..files.object_store import InvalidObjectKey, public_object_key

router = APIRouter(tags=["files"])


@router.get("/files/{key:path}", response_class=FileResponse)
async def get_file(key: str) -> FileResponse:
    """Resolve one relative object key through the configured ObjectStore."""
    try:
        object_key = public_object_key(key)
        path = get_object_store().resolve(object_key)
    except (InvalidObjectKey, ValueError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found") from error
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if media_type == "application/pdf":
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    inline = media_type.startswith("image/") or media_type == "application/pdf"
    headers = {"X-Content-Type-Options": "nosniff"}
    if inline:
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="inline" if inline else "attachment",
        headers=headers,
    )

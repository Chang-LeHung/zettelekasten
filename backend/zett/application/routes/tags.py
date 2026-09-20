"""Persistent library tag taxonomy endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from ...schemas import AgentArtifactEntity, TagEntity, TagTreeEntity
from ..schemas import ArtifactTagsIn, TagCreateIn, TagUpdateIn
from ..tagging import tag_service

router = APIRouter(prefix="/library/tags", tags=["library-tags"])


@router.get("", response_model=list[TagTreeEntity])
async def list_tags() -> list[TagTreeEntity]:
    """Return the complete stable taxonomy with direct and descendant counts."""
    return await tag_service.list_tree()


@router.post("", response_model=TagEntity, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreateIn) -> TagEntity:
    """Create a path and any missing parent nodes."""
    try:
        return await tag_service.create_path(
            payload.path,
            description=payload.description,
            color=payload.color,
        )
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.put("/{tag_id}", response_model=TagEntity)
async def update_tag(tag_id: str, payload: TagUpdateIn) -> TagEntity:
    """Rename, move, or restyle one leaf tag."""
    try:
        return await tag_service.update(
            tag_id,
            path=payload.path,
            description=payload.description,
            color=payload.color,
        )
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: str,
    recursive: bool = Query(default=False),
    force: bool = Query(default=False),
) -> dict[str, bool]:
    """Delete an unused tag, requiring explicit flags for children or assignments."""
    try:
        return {"ok": await tag_service.delete(tag_id, recursive=recursive, force=force)}
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.put("/artifacts/{artifact_id}", response_model=AgentArtifactEntity)
async def replace_artifact_tags(artifact_id: str, payload: ArtifactTagsIn) -> AgentArtifactEntity:
    """Replace the confirmed classification of one saved artifact."""
    try:
        return await tag_service.replace_artifact_tags(artifact_id, payload.paths)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

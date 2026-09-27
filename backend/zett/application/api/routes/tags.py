"""Persistent library tag taxonomy endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from ....schemas import AgentArtifactEntity, TagEntity, TagTreeEntity
from ...tags.tagging import tag_service
from ..schemas import ArtifactTagsIn, TagCreateIn, TagUpdateIn

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


@router.get("/{tag_id}", response_model=TagEntity)
async def get_tag(tag_id: str) -> TagEntity:
    """Read one tag by id."""
    try:
        return await tag_service.require(tag_id)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


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
    """Replace the confirmed classification of one saved artifact.

    The caller states the complete set, which is what an editor does when it
    saves a classification. A shell that only knows one tag it wants to add or
    remove uses the id-scoped routes below instead of reading and rewriting the
    whole set.
    """
    try:
        return await tag_service.replace_artifact_tags(artifact_id, payload.paths)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.put("/{tag_id}/artifacts/{artifact_id}", response_model=AgentArtifactEntity)
async def assign_tag_to_artifact(tag_id: str, artifact_id: str) -> AgentArtifactEntity:
    """Attach one tag to one artifact, keeping that artifact's other tags."""
    try:
        return await tag_service.assign_tag(artifact_id, tag_id)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.delete("/{tag_id}/artifacts/{artifact_id}", response_model=AgentArtifactEntity)
async def unassign_tag_from_artifact(tag_id: str, artifact_id: str) -> AgentArtifactEntity:
    """Detach one tag from one artifact, keeping that artifact's other tags."""
    try:
        return await tag_service.unassign_tag(artifact_id, tag_id)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

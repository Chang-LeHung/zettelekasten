"""Asynchronous endpoints for card, article, image, and slide artifacts."""

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, Response

from ...infra.dao import artifact_storage, session_storage
from ...models import ArtifactListOptions
from ...schemas import AgentArtifact, AgentArtifactWrite, ArtifactStatus, ArtifactType
from ..dependencies import run_sync
from ..latex_artifacts import get_latex_pdf
from ..schemas import ArtifactCreateIn, ArtifactUpdateIn, DeleteResponse
from ..tagging import tag_service

router = APIRouter(tags=["artifacts"])


@router.get("/agent/{session_id}/artifacts/{artifact_id}/content", response_class=FileResponse)
async def get_artifact_pdf(session_id: str, artifact_id: str) -> Response:
    """Resolve a session-owned compiled PDF for inline preview."""
    try:
        path = await run_sync(get_latex_pdf, session_id, artifact_id)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact PDF not found") from error
    if path is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "no-store"})
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.get("/artifacts", response_model=list[AgentArtifact])
async def list_all_artifacts(
    q: str | None = None,
    artifact_types: list[ArtifactType] = Query(default=[]),
    statuses: list[ArtifactStatus] = Query(default=[]),
    tag_ids: list[str] = Query(default=[]),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AgentArtifact]:
    """Search artifacts across sessions for the library UI."""
    await run_sync(tag_service.backfill_legacy_artifacts)
    try:
        expanded_tag_ids = await run_sync(tag_service.subtree_ids, tag_ids) if tag_ids else ()
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    options = ArtifactListOptions(
        query=q,
        artifact_types=tuple(item.value for item in artifact_types),
        statuses=tuple(item.value for item in statuses),
        tag_ids=expanded_tag_ids,
        limit=limit,
        offset=offset,
    )
    return await run_sync(artifact_storage.list, options)


@router.get("/agent/{session_id}/artifacts", response_model=list[AgentArtifact])
async def list_session_artifacts(session_id: str) -> list[AgentArtifact]:
    """List every artifact belonging to one conversation."""
    if await run_sync(session_storage.get, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return await run_sync(artifact_storage.list, ArtifactListOptions(session_id=session_id, limit=500))


@router.post(
    "/agent/{session_id}/artifacts",
    response_model=AgentArtifact,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact(session_id: str, payload: ArtifactCreateIn) -> AgentArtifact:
    """Create one typed artifact owned by the URL session."""
    if await run_sync(session_storage.get, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=payload.content,
        raw_content=payload.raw_content,
        status=payload.status,
        metadata=payload.metadata,
    )
    try:
        created = await run_sync(artifact_storage.create, entity)
        return await run_sync(tag_service.sync_confirmed_suggestions, created)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/agent/{session_id}/artifacts/{artifact_id}", response_model=AgentArtifact)
async def get_artifact(session_id: str, artifact_id: str) -> AgentArtifact:
    artifact = await run_sync(artifact_storage.get_for_session, session_id, artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return artifact


@router.put("/agent/{session_id}/artifacts/{artifact_id}", response_model=AgentArtifact)
async def update_artifact(session_id: str, artifact_id: str, payload: ArtifactUpdateIn) -> AgentArtifact:
    """Replace editable content while preserving lifecycle and metadata."""
    current = await run_sync(artifact_storage.get_for_session, session_id, artifact_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=payload.content,
        raw_content=current.raw_content,
        status=current.status,
        metadata=current.metadata,
    )
    try:
        updated = await run_sync(artifact_storage.update, artifact_id, entity)
        return await run_sync(tag_service.sync_confirmed_suggestions, updated)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.post("/agent/{session_id}/artifacts/{artifact_id}/save", response_model=AgentArtifact)
async def save_artifact(session_id: str, artifact_id: str) -> AgentArtifact:
    """Move a draft artifact into the durable saved library."""
    current = await run_sync(artifact_storage.get_for_session, session_id, artifact_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=current.content,
        raw_content=current.raw_content,
        status=ArtifactStatus.SAVED,
        metadata=current.metadata,
    )
    try:
        saved = await run_sync(artifact_storage.update, artifact_id, entity)
        return await run_sync(tag_service.sync_confirmed_suggestions, saved)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.delete("/agent/{session_id}/artifacts/{artifact_id}", response_model=DeleteResponse)
async def delete_artifact(session_id: str, artifact_id: str) -> DeleteResponse:
    """Delete an artifact only when it belongs to the path session."""
    current = await run_sync(artifact_storage.get_for_session, session_id, artifact_id)
    if current is None:
        return DeleteResponse(ok=False)
    return DeleteResponse(ok=await run_sync(artifact_storage.delete, artifact_id))

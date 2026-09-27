"""Asynchronous endpoints for card, article, image, and slide artifacts."""

from fastapi import APIRouter, HTTPException, Query, status

from ....infra.persistence.dao import artifact_storage, session_storage
from ....schemas import AgentArtifactEntity, AgentArtifactWrite, ArtifactListOptions, ArtifactStatus, ArtifactType
from ...artifacts.library import library_session_service
from ...artifacts.versioning import UncommittedLatexProjectError, artifact_versioning
from ...tags.tagging import tag_service
from ..schemas import ArtifactCreateIn, ArtifactUpdateIn, DeleteResponse

router = APIRouter(tags=["artifacts"])


async def _require_committed_project(artifact: AgentArtifactEntity) -> None:
    """Refuse to publish a LaTeX project whose changes nobody committed yet."""
    try:
        await artifact_versioning.verify(artifact)
    except UncommittedLatexProjectError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.get("/artifacts", response_model=list[AgentArtifactEntity])
async def list_all_artifacts(
    q: str | None = None,
    artifact_types: list[ArtifactType] = Query(default=[]),
    statuses: list[ArtifactStatus] = Query(default=[]),
    tag_ids: list[str] = Query(default=[]),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AgentArtifactEntity]:
    """Search artifacts across sessions for the library UI."""
    try:
        expanded_tag_ids = await tag_service.subtree_ids(tag_ids) if tag_ids else ()
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
    return await artifact_storage.list(options)


@router.get("/agent/{session_id}/artifacts", response_model=list[AgentArtifactEntity])
async def list_session_artifacts(session_id: str) -> list[AgentArtifactEntity]:
    """List every artifact belonging to one conversation."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return await artifact_storage.list(ArtifactListOptions(session_id=session_id, limit=500))


@router.post(
    "/agent/{session_id}/artifacts",
    response_model=AgentArtifactEntity,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact(session_id: str, payload: ArtifactCreateIn) -> AgentArtifactEntity:
    """Create one typed artifact owned by the URL session."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return await _create_artifact(session_id, payload)


@router.post("/artifacts", response_model=AgentArtifactEntity, status_code=status.HTTP_201_CREATED)
async def create_library_artifact(payload: ArtifactCreateIn) -> AgentArtifactEntity:
    """Create one artifact that belongs to no conversation.

    A shell or a script has no session to create into, so the server owns that
    decision: the artifact is persisted under the hidden library session, which
    the sidebar never lists but the library view reads like any other owner.

    A session-owned artifact is attributed to its conversation. One created
    without a conversation has nothing else to name its creator, so this route
    requires ``metadata.source`` — who created it — and refuses a blank one.
    """
    source = _library_source(payload)
    attributed = payload.model_copy(update={"metadata": {**payload.metadata, "source": source}})
    return await _create_artifact(await library_session_service.get_or_create(), attributed)


def _library_source(payload: ArtifactCreateIn) -> str:
    """Return the trimmed ``metadata.source`` of a library artifact, or refuse it.

    Provenance is the point of the library session: it has no conversation to
    attribute an artifact to, so an empty ``source`` would leave an artifact
    nobody can account for. The check lives here rather than in the CLI because
    the endpoint is also reachable with ``curl`` and from any script.
    """
    source = payload.metadata.get("source")
    if not isinstance(source, str) or not source.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "metadata.source is required: name who creates this artifact",
        )
    return source.strip()


async def _create_artifact(session_id: str, payload: ArtifactCreateIn) -> AgentArtifactEntity:
    """Persist one typed artifact for an existing session and sync its tags."""
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=payload.content,
        draft_content=payload.content,
        raw_content=payload.raw_content,
        status=payload.status,
        metadata=payload.metadata,
    )
    try:
        created = await artifact_storage.create(entity)
        return await tag_service.sync_confirmed_suggestions(created)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/artifacts/{artifact_id}", response_model=AgentArtifactEntity)
async def get_library_artifact(artifact_id: str) -> AgentArtifactEntity:
    """Read one artifact by id, whichever session owns it."""
    artifact = await artifact_storage.get(artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return artifact


@router.delete("/artifacts/{artifact_id}", response_model=DeleteResponse)
async def delete_library_artifact(artifact_id: str) -> DeleteResponse:
    """Delete one artifact from the library, and nothing outside it.

    Only an artifact this library session owns can be deleted here. Ownership
    decides, not the caller: an artifact a conversation owns is deleted through
    that conversation's route, refused with 403 here, and left untouched, so a
    library client — the CLI included — can never remove a chat's artifact by
    naming its id. A missing artifact answers 404 and a foreign one answers 403,
    which is the difference a script needs to tell "gone already" from "not
    mine to delete".
    """
    artifact = await artifact_storage.get(artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    owner = await library_session_service.current()
    if owner is None or artifact.session_id != owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Artifact belongs to a conversation; delete it through that conversation",
        )
    return DeleteResponse(ok=await artifact_storage.delete(artifact_id))


@router.get("/agent/{session_id}/artifacts/{artifact_id}", response_model=AgentArtifactEntity)
async def get_artifact(session_id: str, artifact_id: str) -> AgentArtifactEntity:
    artifact = await artifact_storage.get_for_session(session_id, artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return artifact


@router.put("/agent/{session_id}/artifacts/{artifact_id}", response_model=AgentArtifactEntity)
async def update_artifact(session_id: str, artifact_id: str, payload: ArtifactUpdateIn) -> AgentArtifactEntity:
    """Write user-edited content, replacing any draft the model proposed.

    The editor's save is a user action, so it publishes directly and mirrors the
    published content into the draft, which keeps the draft as the working copy.
    """
    current = await artifact_storage.get_for_session(session_id, artifact_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    await _require_committed_project(current)
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=payload.content,
        draft_content=payload.content,
        raw_content=current.raw_content,
        status=current.status,
        metadata=current.metadata,
    )
    try:
        updated = await artifact_storage.update(artifact_id, entity)
        return await tag_service.sync_confirmed_suggestions(updated)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.put("/agent/{session_id}/artifacts/{artifact_id}/draft", response_model=AgentArtifactEntity)
async def update_artifact_draft(
    session_id: str,
    artifact_id: str,
    payload: ArtifactUpdateIn,
) -> AgentArtifactEntity:
    """Write an edited draft without touching the published artifact.

    Every editing surface lands here: the conversation panel, its full editor,
    and the model's own tools. The save endpoint is what publishes a draft.
    """
    current = await artifact_storage.get_for_session(session_id, artifact_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=current.content,
        draft_content=payload.content,
        raw_content=current.raw_content,
        status=current.status,
        metadata=current.metadata,
    )
    try:
        return await artifact_storage.update(artifact_id, entity)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.post("/agent/{session_id}/artifacts/{artifact_id}/save", response_model=AgentArtifactEntity)
async def save_artifact(session_id: str, artifact_id: str) -> AgentArtifactEntity:
    """Publish the pending draft as this artifact's content and mark it saved.

    This is the user's explicit approval step: the model only ever writes draft
    content, and nothing it produced becomes the artifact's content until this
    request arrives from the browser. The draft keeps a copy of the published
    content so the model always reads its working copy from ``draft_content``.
    """
    current = await artifact_storage.get_for_session(session_id, artifact_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    published = current.draft_content or current.content
    if published is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Artifact has no content to save")
    await _require_committed_project(current)
    entity = AgentArtifactWrite(
        session_id=session_id,
        content=published,
        draft_content=published,
        raw_content=current.raw_content,
        status=ArtifactStatus.SAVED,
        metadata=current.metadata,
    )
    try:
        saved = await artifact_storage.update(artifact_id, entity)
        return await tag_service.sync_confirmed_suggestions(saved)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.delete("/agent/{session_id}/artifacts/{artifact_id}", response_model=DeleteResponse)
async def delete_artifact(session_id: str, artifact_id: str) -> DeleteResponse:
    """Delete an artifact only when it belongs to the path session."""
    current = await artifact_storage.get_for_session(session_id, artifact_id)
    if current is None:
        return DeleteResponse(ok=False)
    return DeleteResponse(ok=await artifact_storage.delete(artifact_id))

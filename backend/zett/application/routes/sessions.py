"""Asynchronous session and immutable-message endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Query, status

from ...agent.config import SYSTEM_PROMPT
from ...infra.agent_runtime import get_agent_runtime_storage
from ...infra.dao import artifact_storage, session_asset_storage, session_storage
from ...models import ArtifactListOptions, SessionAssetListOptions, SessionListOptions
from ...schemas import AgentSessionCreate
from ..dependencies import run_sync
from ..presentation import message_out, session_out
from ..schemas import AgentStartOut, DeleteResponse, PersistedMessageOut, SessionOut
from ..session_context import SessionContextComposition, session_context_composition_service
from ..session_preferences import SessionModelPreference, session_model_preference_service

router = APIRouter(prefix="/agent", tags=["sessions"])


async def _session_detail(session_id: str) -> SessionOut:
    summary = await session_storage.get(session_id)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    messages, artifacts, assets = await asyncio.gather(
        session_storage.list_raw_messages(session_id, limit=10_000),
        run_sync(artifact_storage.list, ArtifactListOptions(session_id=session_id, limit=500)),
        run_sync(session_asset_storage.list, SessionAssetListOptions(session_id=session_id, limit=500)),
    )
    result = session_out(summary)
    result.messages = [message_out(record) for record in messages]
    result.artifacts = artifacts
    result.assets = assets
    return result


@router.post("/start", response_model=AgentStartOut, status_code=status.HTTP_201_CREATED)
async def start_session() -> AgentStartOut:
    """Create an empty root conversation before its first streamed turn."""
    session = await session_storage.create(AgentSessionCreate())
    return AgentStartOut(conversation_id=session.session_id)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SessionOut]:
    """List lightweight session summaries in latest-activity order."""
    sessions = await session_storage.list(SessionListOptions(limit=limit, offset=offset))
    return [session_out(item) for item in sessions]


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: str) -> SessionOut:
    """Load one conversation with raw messages, artifacts, and assets."""
    return await _session_detail(session_id)


@router.get("/sessions/{session_id}/model", response_model=SessionModelPreference | None)
async def get_session_model(session_id: str) -> SessionModelPreference | None:
    """Return the provider configuration most recently used by this session."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return await run_sync(session_model_preference_service.get, session_id)


@router.get("/sessions/{session_id}/context-composition", response_model=SessionContextComposition)
async def get_session_context_composition(session_id: str) -> SessionContextComposition:
    """Return the last live context ratios, estimating sessions created before the feature."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    storage = await run_sync(get_agent_runtime_storage)
    return await session_context_composition_service.get_or_estimate(session_id, storage, SYSTEM_PROMPT)


@router.get("/sessions/{session_id}/messages", response_model=list[PersistedMessageOut])
async def list_session_messages(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[PersistedMessageOut]:
    """Page through the immutable Raw Log used by the conversation UI."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    records = await session_storage.list_raw_messages(session_id, limit=limit, offset=offset)
    return [message_out(record) for record in records]


@router.patch("/sessions/{session_id}/title", response_model=SessionOut)
async def update_session_title(session_id: str, payload: AgentSessionCreate) -> SessionOut:
    """Update the title without rebuilding the full conversation."""
    try:
        updated = await session_storage.update(session_id, payload)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found") from error
    return session_out(updated)


@router.delete("/sessions/{session_id}", response_model=DeleteResponse)
async def delete_session(session_id: str) -> DeleteResponse:
    """Explicitly delete a session and its owned assets and artifacts."""
    deleted = await session_storage.delete(session_id)
    if deleted:
        await asyncio.gather(
            run_sync(session_model_preference_service.delete, session_id),
            run_sync(session_context_composition_service.delete, session_id),
        )
    return DeleteResponse(ok=deleted)

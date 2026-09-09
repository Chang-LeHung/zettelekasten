"""Asynchronous Zettelkasten Agent streaming and external-event endpoints."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from zett_agent import (
    AgentConfig,
    ExternalEvent,
    ReasoningEffort,
    new_uuid7,
)

from ...agent import ZettelkastenEventDispatcher, encode_sse, get_zettelkasten_agent
from ...agent.model_factory import create_model
from ...infra.dao import provider_storage, session_storage
from ...infra.log import get_logger
from ..dependencies import run_sync
from ..schemas import AnalyzeRequest, ExternalEventIn, ExternalEventOut

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)


class ActiveRequestRegistry:
    """Route external UI events to one active request per session."""

    def __init__(self) -> None:
        self._requests: dict[str, AgentConfig] = {}
        self._lock = asyncio.Lock()

    async def add(self, config: AgentConfig) -> None:
        async with self._lock:
            if config.session_id in self._requests:
                raise HTTPException(status.HTTP_409_CONFLICT, "This session already has an active request")
            self._requests[config.session_id] = config

    async def remove(self, config: AgentConfig) -> None:
        async with self._lock:
            if self._requests.get(config.session_id) == config:
                self._requests.pop(config.session_id)

    async def emit(self, session_id: str, event: ExternalEvent) -> list[str] | None:
        async with self._lock:
            config = self._requests.get(session_id)
        if config is None:
            return None
        return get_zettelkasten_agent().emit_external_event(event, config=config)


active_requests = ActiveRequestRegistry()


@router.post("/{session_id}/messages")
async def stream_message(session_id: str, payload: AnalyzeRequest) -> StreamingResponse:
    """Run one user turn and stream lossless zett-agent events as SSE."""
    if await run_sync(session_storage.get, session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    connection = await run_sync(provider_storage.resolve_connection, payload.provider_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enabled provider not found")
    try:
        effort = ReasoningEffort(payload.reasoning_effort)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported reasoning effort") from error

    model = create_model(connection)
    frames: deque[str] = deque()

    async def send(frame: str) -> None:
        frames.append(frame)

    config = AgentConfig(session_id=session_id, request_id=new_uuid7())
    agent = get_zettelkasten_agent()
    client = agent.client(ZettelkastenEventDispatcher(send))
    try:
        await active_requests.add(config)
    except Exception:
        await model.aclose()
        raise

    async def body() -> AsyncIterator[str]:
        try:
            async for _ in client.stream(
                payload.current_message,
                config=config,
                model=model,
                reasoning_effort=effort,
                metadata=payload.metadata,
                tags=payload.tags,
            ):
                while frames:
                    yield frames.popleft()
            while frames:
                yield frames.popleft()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Agent stream failed; session_id=%s", session_id)
            yield encode_sse("error", {"type": type(error).__name__, "message": str(error)})
        finally:
            await active_requests.remove(config)
            await model.aclose()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/events", response_model=ExternalEventOut)
async def emit_external_event(session_id: str, payload: ExternalEventIn) -> ExternalEventOut:
    """Broadcast one UI response to extensions of the active session request."""
    accepted_by = await active_requests.emit(session_id, ExternalEvent(name=payload.name, payload=payload.payload))
    if accepted_by is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session has no active request")
    return ExternalEventOut(accepted=bool(accepted_by), accepted_by=accepted_by)

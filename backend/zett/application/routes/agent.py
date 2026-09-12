"""Asynchronous Zettelkasten Agent streaming and external-event endpoints."""

import asyncio
import base64
import binascii
from collections import deque
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from zett_agent import (
    AgentEventType,
    AgentRunConfig,
    ExternalEvent,
    ImageBytesSource,
    ImageContent,
    ReasoningEffort,
    TextContent,
    UserMessage,
    new_uuid7,
)

from ...agent import ZettelkastenEventDispatcher, encode_sse, get_zettelkasten_agent
from ...agent.model_factory import create_model
from ...config import settings
from ...infra.dao import provider_storage, session_storage
from ...infra.log import get_logger
from ..dependencies import run_sync
from ..schemas import AnalyzeRequest, ExternalEventIn, ExternalEventOut, MessageImagePartIn, MessageTextPartIn
from ..session_titles import generate_initial_session_title
from ..settings import runtime_settings_service

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)


class ActiveRequestRegistry:
    """Route external UI events to one active request per session."""

    def __init__(self) -> None:
        self._requests: dict[str, AgentRunConfig] = {}
        self._lock = asyncio.Lock()

    async def add(self, config: AgentRunConfig) -> None:
        async with self._lock:
            if config.session_id in self._requests:
                raise HTTPException(status.HTTP_409_CONFLICT, "This session already has an active request")
            self._requests[config.session_id] = config

    async def remove(self, config: AgentRunConfig) -> None:
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


def _user_message(payload: AnalyzeRequest, *, max_images: int) -> UserMessage:
    """Decode bounded browser images into one provider-neutral multimodal turn."""
    parts: list[TextContent | ImageContent] = []
    total_size = 0
    image_count = 0
    for part in payload.parts or ([MessageTextPartIn(text=payload.current_message)] if payload.current_message else []):
        match part:
            case MessageTextPartIn(text=text):
                if text:
                    parts.append(TextContent(text))
            case MessageImagePartIn() as image:
                image_count += 1
                if image_count > max_images:
                    image_label = "image" if max_images == 1 else "images"
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        f"A message can contain up to {max_images} {image_label}",
                    )
                try:
                    content = base64.b64decode(image.data_base64, validate=True)
                except (ValueError, binascii.Error) as error:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid image data: {image.name}"
                    ) from error
                if not content:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Image is empty: {image.name}")
                total_size += len(content)
                if total_size > settings.max_asset_size_bytes:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Message images exceed the configured limit")
                parts.append(ImageContent(source=ImageBytesSource(content, image.mime_type), alt_text=image.name))
    return UserMessage(content=parts)


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
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported reasoning effort") from error

    runtime_settings = await run_sync(runtime_settings_service.get)
    user_message = _user_message(payload, max_images=runtime_settings.max_message_images)
    model = create_model(connection)
    frames: deque[str] = deque()

    async def send(frame: str) -> None:
        frames.append(frame)

    config = AgentRunConfig(session_id=session_id, request_id=new_uuid7())
    agent = get_zettelkasten_agent()
    client = agent.client(ZettelkastenEventDispatcher(send))
    run_completed = False
    try:
        await active_requests.add(config)
    except Exception:
        await model.aclose()
        raise

    async def body() -> AsyncIterator[str]:
        nonlocal run_completed
        try:
            async for event in client.stream(
                user_message,
                config=config,
                model=model,
                reasoning_effort=effort,
                metadata=payload.metadata,
                tags=payload.tags,
            ):
                if event.type is AgentEventType.RUN_COMPLETED:
                    run_completed = True
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

    async def title_after_success() -> None:
        if run_completed:
            await generate_initial_session_title(session_id, connection)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(title_after_success),
    )


@router.post("/{session_id}/events", response_model=ExternalEventOut)
async def emit_external_event(session_id: str, payload: ExternalEventIn) -> ExternalEventOut:
    """Broadcast one UI response to extensions of the active session request."""
    accepted_by = await active_requests.emit(session_id, ExternalEvent(name=payload.name, payload=payload.payload))
    if accepted_by is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session has no active request")
    return ExternalEventOut(accepted=bool(accepted_by), accepted_by=accepted_by)

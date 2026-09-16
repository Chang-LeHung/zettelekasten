"""Asynchronous Zettelkasten Agent streaming and external-event endpoints."""

import asyncio
import base64
import binascii
from collections import deque
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from zett_agent import (
    AgentClient,
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

from ...agent import ZettelkastenAgent, ZettelkastenAgentConfig, ZettelkastenEventDispatcher, encode_sse
from ...agent.model_factory import ProviderAdapter, create_model
from ...config import settings
from ...infra.agent_runtime import get_agent_runtime_storage
from ...infra.dao import provider_storage, session_storage
from ...infra.log import get_logger
from ...schemas import ProviderConnection
from ..dependencies import run_sync
from ..schemas import AnalyzeRequest, ExternalEventIn, ExternalEventOut, MessageImagePartIn, MessageTextPartIn
from ..session_context import session_context_composition_service
from ..session_preferences import session_model_preference_service
from ..session_titles import generate_initial_session_title
from ..settings import runtime_settings_service

router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)


class ActiveRequestRegistry:
    """Reserve one pending request per session and route its UI events.

    A reservation is created before the request-owned Model and Agent. This
    closes the construction race where two requests could both observe an idle
    session and allocate runtimes before either Agent marked itself pending.
    Presence in this registry therefore means ``pending``, including the short
    setup window before the Agent is bound.
    """

    def __init__(self) -> None:
        self._requests: dict[str, _ActiveRequest] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, config: AgentRunConfig) -> None:
        """Atomically claim a session before constructing request resources."""
        async with self._lock:
            if config.session_id in self._requests:
                raise HTTPException(status.HTTP_409_CONFLICT, "This session already has an active request")
            self._requests[config.session_id] = _ActiveRequest(config)

    async def bind(self, config: AgentRunConfig, agent: ZettelkastenAgent) -> None:
        """Attach the initialized Agent to its existing reservation."""
        async with self._lock:
            active = self._requests.get(config.session_id)
            if active is None or active.config != config:
                raise RuntimeError("Cannot bind an Agent without its active request reservation")
            active.agent = agent

    async def pending(self, session_id: str) -> bool:
        """Return whether setup or execution currently owns this session."""
        async with self._lock:
            return session_id in self._requests

    async def remove(self, config: AgentRunConfig) -> None:
        """Release only the reservation owned by this exact request."""
        async with self._lock:
            active = self._requests.get(config.session_id)
            if active is not None and active.config == config:
                self._requests.pop(config.session_id)

    async def emit(self, session_id: str, event: ExternalEvent) -> list[str] | None:
        """Send external input to the active Agent once setup has completed."""
        async with self._lock:
            active = self._requests.get(session_id)
        if active is None:
            return None
        if active.agent is None:
            return []
        return active.agent.emit_external_event(event, config=active.config)


@dataclass(slots=True)
class _ActiveRequest:
    """One pending session reservation, optionally bound to its runtime."""

    config: AgentRunConfig
    agent: ZettelkastenAgent | None = None


@dataclass(slots=True)
class _PreparedAgentRequest:
    """Validated request plus every request-owned streaming resource."""

    config: AgentRunConfig
    connection: ProviderConnection
    model: ProviderAdapter
    client: AgentClient
    message: UserMessage
    effort: ReasoningEffort
    frames: deque[str]


active_requests = ActiveRequestRegistry()


async def _remember_context_composition(session_id: str, ratios: dict[str, float]) -> None:
    """Persist an auxiliary UI metric without failing the active Agent request."""
    try:
        await run_sync(session_context_composition_service.remember, session_id, ratios)
    except Exception:
        logger.exception("Could not persist context composition; session_id=%s", session_id)


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


async def _prepare_agent_request(session_id: str, payload: AnalyzeRequest) -> _PreparedAgentRequest:
    """Validate input, reserve its session, and construct request-owned resources."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    connection = await run_sync(provider_storage.resolve_connection, payload.provider_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enabled provider not found")
    try:
        effort = ReasoningEffort(payload.reasoning_effort)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported reasoning effort") from error

    runtime_settings = await run_sync(runtime_settings_service.get)
    message = _user_message(payload, max_images=runtime_settings.max_message_images)
    config = AgentRunConfig(session_id=session_id, request_id=new_uuid7())
    await active_requests.reserve(config)
    model: ProviderAdapter | None = None
    try:
        model = create_model(connection)
        frames: deque[str] = deque()

        async def send(frame: str) -> None:
            frames.append(frame)

        storage = await run_sync(get_agent_runtime_storage)
        # Reserve the session before binding the Agent, allowing each new Agent
        # instance to apply the latest configuration immediately.
        agent = await ZettelkastenAgentConfig(
            session_id=session_id,
            max_iterations=runtime_settings.max_turn_iterations,
            compaction_max_tokens=runtime_settings.compaction_max_tokens,
            compaction_keep_recent_tokens=runtime_settings.compaction_keep_recent_tokens,
            context_composition_recorder=_remember_context_composition,
        ).create(storage)
        await active_requests.bind(config, agent)
        # Remember only a fully prepared request. Validation, Model creation,
        # Agent construction, and registry binding may all fail before this.
        await run_sync(session_model_preference_service.remember, session_id, connection)
        return _PreparedAgentRequest(
            config=config,
            connection=connection,
            model=model,
            client=agent.client(ZettelkastenEventDispatcher(send)),
            message=message,
            effort=effort,
            frames=frames,
        )
    except BaseException:
        # Setup happens before StreamingResponse owns a body iterator, so this
        # branch must undo the reservation and close a partially created Model.
        await active_requests.remove(config)
        if model is not None:
            await model.aclose()
        raise


@router.post("/{session_id}/messages")
async def stream_message(session_id: str, payload: AnalyzeRequest) -> StreamingResponse:
    """Run one user turn and stream lossless zett-agent events as SSE."""
    request = await _prepare_agent_request(session_id, payload)
    run_completed = False

    async def body() -> AsyncIterator[str]:
        nonlocal run_completed
        try:
            # Explicit closure matters when Starlette cancels this body because
            # the browser disconnected. AgentClient then closes Agent.stream(),
            # which publishes cancellation and unwinds pending extension waits.
            async with aclosing(
                request.client.stream(
                    request.message,
                    config=request.config,
                    model=request.model,
                    reasoning_effort=request.effort,
                    metadata=payload.metadata,
                    tags=payload.tags,
                )
            ) as events:
                async for event in events:
                    if event.type is AgentEventType.RUN_COMPLETED:
                        run_completed = True
                        # Agent persistence and terminal hooks are complete before
                        # this event. Release now rather than waiting for the HTTP
                        # client to drain buffered SSE frames, which may be slow.
                        await active_requests.remove(request.config)
                    while request.frames:
                        yield request.frames.popleft()
            while request.frames:
                yield request.frames.popleft()
        except asyncio.CancelledError, GeneratorExit:
            # Disconnects and explicit iterator closure are control flow, not
            # application errors: never attempt to yield an SSE error frame.
            raise
        except Exception as error:
            # Provider, tool, dispatcher, and persistence failures remain visible
            # to the browser while the finally branch releases request ownership.
            logger.exception("Agent stream failed; session_id=%s", session_id)
            yield encode_sse("error", {"type": type(error).__name__, "message": str(error)})
        finally:
            # Idempotent removal covers success, setup-independent stream errors,
            # client disconnects, explicit aclose(), and task cancellation.
            await active_requests.remove(request.config)
            await request.model.aclose()

    async def title_after_success() -> None:
        if run_completed:
            await generate_initial_session_title(session_id, request.connection)

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

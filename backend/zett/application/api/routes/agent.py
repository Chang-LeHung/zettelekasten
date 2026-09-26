"""Asynchronous Zettelkasten Agent streaming and external-event endpoints."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from zett_agent import (
    STEERING_MESSAGE_EVENT_NAME,
    AgentClient,
    AgentEvent,
    AgentEventType,
    AgentRunConfig,
    ExternalEvent,
    ReasoningEffort,
    ShellApprovalMode,
    UserMessage,
)

from ....agent import (
    AtCommandInvocation,
    SlashCommandInvocation,
    ZettelkastenAgent,
    ZettelkastenAgentConfig,
    ZettelkastenEventDispatcher,
    encode_sse,
    event_payload,
)
from ....agent.model_factory import ProviderAdapter, create_model
from ....infra.agent.runtime import get_agent_runtime_storage
from ....infra.agent.shell_approval import shell_approval_storage
from ....infra.log import get_logger, log_preview
from ....infra.persistence.dao import model_usage_activity_storage, provider_storage, session_storage
from ....messages import MessageImageSizeExceeded, MessagePartCodec, MessagePartError
from ....schemas import ProviderConnection
from ...agent.session_context import session_context_composition_service
from ...agent.session_preferences import session_model_preference_service
from ...agent.session_titles import generate_initial_session_title
from ...agent.turns import AgentTurn
from ...assets.message_files import store_message_images
from ...runtime.settings import RuntimeSettings, runtime_settings_service
from ..schemas import (
    AnalyzeRequest,
    AtCommandOut,
    ExternalEventIn,
    ExternalEventOut,
    SlashCommandOut,
    SteerRequest,
    UserMessageIn,
)

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
    agent: ZettelkastenAgent
    connection: ProviderConnection
    model: ProviderAdapter
    client: AgentClient
    message: UserMessage
    effort: ReasoningEffort


active_requests = ActiveRequestRegistry()


async def _remember_context_composition(session_id: str, ratios: dict[str, float]) -> None:
    """Persist an auxiliary UI metric without failing the active Agent request."""
    try:
        await session_context_composition_service.remember(session_id, ratios)
    except Exception:
        logger.exception("Could not persist context composition; session_id=%s", session_id)


def _agent_config(session_id: str, runtime_settings: RuntimeSettings) -> ZettelkastenAgentConfig:
    """Build one request-scoped container configuration."""
    return ZettelkastenAgentConfig(
        session_id=session_id,
        max_iterations=runtime_settings.max_turn_iterations,
        max_asset_size_bytes=runtime_settings.max_asset_size_bytes,
        compaction_max_tokens=runtime_settings.compaction_max_tokens,
        compaction_keep_recent_tokens=runtime_settings.compaction_keep_recent_tokens,
        usage_activity_storage=model_usage_activity_storage,
        shell_approval_storage=shell_approval_storage,
        storage=get_agent_runtime_storage(),
        context_composition_recorder=_remember_context_composition,
    )


async def _container(session_id: str, runtime_settings: RuntimeSettings) -> ZettelkastenAgent:
    """Create one initialized container without constructing a provider model."""
    return await ZettelkastenAgent(_agent_config(session_id, runtime_settings)).initialize()


async def _discard_prepared_request(request: _PreparedAgentRequest) -> None:
    """Release a prepared request when routing fails before streaming starts."""
    await active_requests.remove(request.config)
    await request.model.aclose()


def _user_message(payload: UserMessageIn, *, max_images: int, max_asset_size_bytes: int) -> UserMessage:
    """Validate one browser turn through the shared message part codec."""
    codec = MessagePartCodec(max_images=max_images, max_bytes=max_asset_size_bytes)
    try:
        return codec.to_user_message(payload)
    except MessageImageSizeExceeded as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error
    except MessagePartError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


async def _store_message_images(session_id: str, payload: UserMessageIn) -> None:
    """Persist submitted images as session files without ever dropping the turn.

    The message already carries its images inline, so the files are the model's
    handle on the same bytes rather than the only copy. A storage failure
    therefore degrades the turn instead of rejecting a message the user already
    wrote; the upload directory named in the session-files system message simply
    stays empty for that turn.
    """
    try:
        stored = await store_message_images(session_id, payload)
    except Exception:
        logger.exception("Could not store submitted message images; session_id=%s", session_id)
        return
    if not stored:
        return
    logger.info(
        "Message images stored; session_id=%s files=%d bytes=%d names=%s",
        session_id,
        len(stored),
        sum(item.size_bytes for item in stored if item is not None),
        ", ".join(log_preview(item.name, limit=24) for item in stored if item is not None),
    )


async def _prepare_agent_request(session_id: str, payload: AnalyzeRequest) -> _PreparedAgentRequest:
    """Validate input, reserve its session, and construct request-owned resources."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    connection = await provider_storage.resolve_connection(payload.provider_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enabled provider not found")
    try:
        effort = ReasoningEffort(payload.reasoning_effort)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported reasoning effort") from error

    runtime_settings = await runtime_settings_service.get()
    message = _user_message(
        payload,
        max_images=runtime_settings.max_message_images,
        max_asset_size_bytes=runtime_settings.max_asset_size_bytes,
    )
    await _store_message_images(session_id, payload)
    await shell_approval_storage.set_session_mode(session_id, ShellApprovalMode(payload.shell_approval_mode))
    config = AgentRunConfig(session_id=session_id)
    await active_requests.reserve(config)
    model: ProviderAdapter | None = None
    try:
        model = create_model(connection)

        async def discard_frame(frame: str) -> None:
            del frame

        # Reserve the session before binding the Agent, allowing each new Agent
        # instance to apply the latest configuration immediately.
        agent = ZettelkastenAgent(_agent_config(session_id, runtime_settings))
        await agent.initialize()
        await active_requests.bind(config, agent)
        # Remember only a fully prepared request. Validation, Model creation,
        # Agent construction, and registry binding may all fail before this.
        await session_model_preference_service.remember(session_id, connection)
        return _PreparedAgentRequest(
            config=config,
            agent=agent,
            connection=connection,
            model=model,
            client=agent.client(ZettelkastenEventDispatcher(discard_frame)),
            message=message,
            effort=effort,
        )
    except BaseException:
        # Setup happens before StreamingResponse owns a body iterator, so this
        # branch must undo the reservation and close a partially created Model.
        await active_requests.remove(config)
        if model is not None:
            await model.aclose()
        raise


def _stream_response(
    request: _PreparedAgentRequest,
    session_id: str,
    event_factory: Callable[[], AsyncIterator[AgentEvent]],
) -> StreamingResponse:
    """Stream one prepared Agent event source as the existing SSE protocol."""
    run_completed = False

    async def body() -> AsyncIterator[str]:
        nonlocal run_completed
        try:
            # Explicit closure matters when Starlette cancels this body because
            # the browser disconnected. AgentClient then closes Agent.stream(),
            # which publishes cancellation and unwinds pending extension waits.
            async with aclosing(event_factory()) as events:
                async for event in events:
                    if event.type is AgentEventType.RUN_COMPLETED:
                        run_completed = True
                        # Agent persistence and terminal hooks are complete before
                        # this event. Release now rather than waiting for the HTTP
                        # client to drain the remaining stream, which may be slow.
                        await active_requests.remove(request.config)
                    yield encode_sse(event.type.value, event_payload(event))
        except (asyncio.CancelledError, GeneratorExit):
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


@router.get("/{session_id}/slash-commands", response_model=list[SlashCommandOut])
async def list_slash_commands(session_id: str) -> list[SlashCommandOut]:
    """List container-registered commands available to one conversation."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    runtime_settings = await runtime_settings_service.get()
    container = await _container(session_id, runtime_settings)
    return [
        SlashCommandOut(
            id=command.id,
            name=command.name,
            description=command.description,
            type=command.type,
        )
        for command in container.slash_commands()
    ]


@router.get("/{session_id}/at-commands", response_model=list[AtCommandOut])
async def list_at_commands(session_id: str) -> list[AtCommandOut]:
    """List the conversation resources the browser may reference with ``@``."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    runtime_settings = await runtime_settings_service.get()
    container = await _container(session_id, runtime_settings)
    return [
        AtCommandOut(
            id=item.id,
            kind=item.kind,
            name=item.name,
            label=item.label,
            description=item.description,
        )
        for item in await container.at_commands(session_id)
    ]


@router.post("/{session_id}/slash-commands/{command_id}")
async def stream_slash_command(
    session_id: str,
    command_id: str,
    payload: AnalyzeRequest,
) -> StreamingResponse:
    """Execute one registered slash command and stream its Agent events."""
    request = await _prepare_agent_request(session_id, payload)
    if request.agent.slash_command(command_id) is None:
        await _discard_prepared_request(request)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slash command not found")
    invocation = SlashCommandInvocation(
        session_id=session_id,
        client=request.client,
        message=request.message,
        model=request.model,
        config=request.config,
        reasoning_effort=request.effort,
        metadata=payload.metadata,
        tags=payload.tags,
    )
    return _stream_response(
        request,
        session_id,
        lambda: request.agent.execute_slash_command(command_id, invocation),
    )


@router.post("/{session_id}/at-commands/{item_id}")
async def stream_at_command(
    session_id: str,
    item_id: str,
    payload: AnalyzeRequest,
) -> StreamingResponse:
    """Run the turn that references one conversation resource with ``@``."""
    request = await _prepare_agent_request(session_id, payload)
    item = await request.agent.at_command(session_id, item_id)
    if item is None:
        await _discard_prepared_request(request)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "At command not found")
    invocation = AtCommandInvocation(
        session_id=session_id,
        client=request.client,
        message=request.message,
        model=request.model,
        config=request.config,
        reasoning_effort=request.effort,
        metadata=payload.metadata,
        tags=payload.tags,
        item=item,
    )
    return _stream_response(
        request,
        session_id,
        lambda: request.agent.execute_at_command(invocation),
    )


@router.post("/{session_id}/messages")
async def stream_message(session_id: str, payload: AnalyzeRequest) -> StreamingResponse:
    """Run one user turn and stream lossless zett-agent events as SSE."""
    request = await _prepare_agent_request(session_id, payload)
    turn = AgentTurn(
        session_id=session_id,
        client=request.client,
        message=request.message,
        model=request.model,
        config=request.config,
        reasoning_effort=request.effort,
        metadata=payload.metadata,
        tags=payload.tags,
    )
    return _stream_response(request, session_id, lambda: turn.prompt())


@router.post("/{session_id}/events", response_model=ExternalEventOut)
async def emit_external_event(session_id: str, payload: ExternalEventIn) -> ExternalEventOut:
    """Broadcast one UI response to extensions of the active session request."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    accepted_by = await active_requests.emit(session_id, ExternalEvent(name=payload.name, payload=payload.payload))
    if accepted_by is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session has no active request")
    return ExternalEventOut(accepted=bool(accepted_by), accepted_by=accepted_by)


@router.post("/{session_id}/steer", response_model=ExternalEventOut)
async def steer_active_request(session_id: str, payload: SteerRequest) -> ExternalEventOut:
    """Route one urgent user message to the active Agent request."""
    if await session_storage.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    runtime_settings = await runtime_settings_service.get()
    message = _user_message(
        payload,
        max_images=runtime_settings.max_message_images,
        max_asset_size_bytes=runtime_settings.max_asset_size_bytes,
    )
    accepted_by = await active_requests.emit(
        session_id,
        ExternalEvent(
            name=STEERING_MESSAGE_EVENT_NAME,
            payload={"session_id": session_id, "message": message},
        ),
    )
    if accepted_by is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Session has no active request")
    return ExternalEventOut(accepted=bool(accepted_by), accepted_by=accepted_by)

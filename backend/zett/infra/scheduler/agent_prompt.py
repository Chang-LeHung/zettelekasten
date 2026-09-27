"""Agent-prompt executor for the standalone scheduler worker process."""

from collections.abc import Mapping
from datetime import datetime

from zett_agent.agent import (
    AgentRunConfig,
)
from zett_agent.dispatcher import (
    AgentEventDispatcher,
)
from zett_agent.events import (
    AgentEvent,
)
from zett_agent.extensions.shell_approval import (
    ShellApprovalMode,
)
from zett_agent.messages import (
    ToolMessage,
    UserMessage,
)
from zett_agent.model import (
    ReasoningEffort,
)

from ...agent.config import ZettelkastenAgentConfig
from ...agent.model_factory import create_model
from ...agent.zettelkasten import ZettelkastenAgent
from ...application.agent.session_context import session_context_composition_service
from ...application.runtime.settings import runtime_settings_service
from ...infra.agent.runtime import get_agent_runtime_storage
from ...infra.agent.shell_approval import shell_approval_storage
from ...infra.log import get_logger, log_preview
from ...infra.persistence.dao import (
    model_usage_activity_storage,
    provider_storage,
    session_storage,
)
from ...schemas import (
    AGENT_PROMPT_ACTION_KIND,
    AgentPromptAction,
    AgentSessionCreate,
    JsonValue,
    SessionType,
)
from .contracts import ActionExecutionStatus, ActionExecutor, ActionResult, ExecutionContext

logger = get_logger(__name__)


class ScheduledRunLogDispatcher(AgentEventDispatcher):
    """Write short progress lines so one scheduled run is observable while it works.

    A scheduled run has no browser watching it, so the worker log is the only
    place its prompt, streaming deltas, and tool calls can be seen. Every line is
    capped to a short preview and keyed by task and run id, which is enough to
    tell a working run from a stuck one without flooding the log with a whole
    answer.
    """

    def __init__(self, *, task_id: str, run_id: str) -> None:
        self._task_id = task_id
        self._run_id = run_id
        self._chars = 0

    async def on_text_delta_event(self, event: AgentEvent) -> None:
        """Report one streamed answer fragment with the running answer length."""
        delta = event.delta or ""
        self._chars += len(delta)
        logger.info(
            "Scheduled run delta; task_id=%s run_id=%s delta=%r chars=%d",
            self._task_id,
            self._run_id,
            log_preview(delta),
            self._chars,
        )

    async def on_tool_started_event(self, event: AgentEvent) -> None:
        names = ", ".join(call.name for call in event.tool_calls or ())
        logger.info("Scheduled run tool started; task_id=%s run_id=%s tools=%s", self._task_id, self._run_id, names)

    async def on_tool_completed_event(self, event: AgentEvent) -> None:
        names = ", ".join(call.name for call in event.tool_calls or ())
        logger.info(
            "Scheduled run tool completed; task_id=%s run_id=%s tools=%s result=%r",
            self._task_id,
            self._run_id,
            names,
            _tool_result_preview(event),
        )

    async def on_tool_failed_event(self, event: AgentEvent) -> None:
        """Report a failed tool with its error and whatever result it returned."""
        names = ", ".join(call.name for call in event.tool_calls or ())
        logger.warning(
            "Scheduled run tool failed; task_id=%s run_id=%s tools=%s error=%r result=%r",
            self._task_id,
            self._run_id,
            names,
            log_preview(str(event.error or "")),
            _tool_result_preview(event),
        )


def _tool_result_preview(event: AgentEvent) -> str:
    """Render one tool result as a short, single-line preview.

    ``ToolMessage.text`` is the model-facing text of the result, so an image a
    tool returns is summarized by its text rather than by encoded bytes.
    """
    message = event.message
    if not isinstance(message, ToolMessage):
        return ""
    return log_preview(message.text)


class AgentPromptExecutor(ActionExecutor):
    """Run one headless Zettelkasten Agent prompt from a scheduler worker."""

    action_kind = AGENT_PROMPT_ACTION_KIND

    def validate_payload(self, payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        """Validate the persisted action before constructing a provider model."""
        return AgentPromptAction.model_validate(payload).model_dump(mode="json")

    async def execute(
        self,
        context: ExecutionContext,
        payload: Mapping[str, JsonValue],
    ) -> ActionResult:
        """Create a fresh session and consume one complete Agent response."""
        action = AgentPromptAction.model_validate(payload)
        connection = await provider_storage.resolve_connection(action.provider_id)
        if connection is None:
            raise ValueError("Enabled provider not found")
        try:
            effort = ReasoningEffort(action.reasoning_effort)
        except ValueError as error:
            raise ValueError(f"Unsupported reasoning effort: {action.reasoning_effort}") from error

        session = await session_storage.create(
            AgentSessionCreate(title=context.task_name, session_type=SessionType.SCHEDULED)
        )
        logger.info(
            "Scheduled agent prompt received; task_id=%s task_name=%r run_id=%s session_id=%s provider_id=%s chars=%d prompt=%r",
            context.task_id,
            context.task_name,
            context.run_id,
            session.session_id,
            connection.id,
            len(action.message),
            log_preview(action.message),
        )
        runtime_settings = await runtime_settings_service.get()
        model = create_model(connection)
        dispatcher = ScheduledRunLogDispatcher(task_id=context.task_id, run_id=context.run_id)
        # A scheduled run has no surface that can answer a shell approval, so its
        # session is marked allow-all; nothing in the worker may ever wait.
        await shell_approval_storage.set_session_mode(session.session_id, ShellApprovalMode.ALLOW_ALL)
        try:
            agent = ZettelkastenAgent(
                ZettelkastenAgentConfig(
                    session_id=session.session_id,
                    max_iterations=runtime_settings.max_turn_iterations,
                    max_asset_size_bytes=runtime_settings.max_asset_size_bytes,
                    compaction_max_tokens=runtime_settings.compaction_max_tokens,
                    compaction_keep_recent_tokens=runtime_settings.compaction_keep_recent_tokens,
                    usage_activity_storage=model_usage_activity_storage,
                    shell_approval_storage=shell_approval_storage,
                    storage=get_agent_runtime_storage(),
                    context_composition_recorder=_remember_context_composition,
                    interactive=False,
                    coding_enabled=False,
                    allow_direct_artifact_edits=True,
                )
            )
            await agent.initialize()
            result = await agent.client(dispatcher).run(  # type: ignore[arg-type]
                UserMessage(content=action.message),
                config=AgentRunConfig(session_id=session.session_id, request_id=context.run_id),
                model=model,
                reasoning_effort=effort,
                metadata={
                    "source": "scheduler",
                    "task_id": context.task_id,
                    "run_id": context.run_id,
                    "scheduled_for": _iso(context.scheduled_for),
                },
                tags={"source": "scheduler"},
            )
        finally:
            await model.aclose()
        logger.info(
            "Scheduled agent prompt answered; task_id=%s run_id=%s session_id=%s chars=%d reply=%r",
            context.task_id,
            context.run_id,
            session.session_id,
            len(result.content),
            log_preview(result.content),
        )
        return ActionResult(
            status=ActionExecutionStatus.SUCCEEDED,
            output={
                "session_id": session.session_id,
                "provider_id": connection.id,
                "model": connection.model,
                "content_preview": result.content[:10_000],
            },
        )


async def _remember_context_composition(session_id: str, ratios: dict[str, float]) -> None:
    """Persist context ratios for scheduled sessions through the shared service."""
    try:
        await session_context_composition_service.remember(session_id, ratios)
    except Exception:
        logger.exception("Could not persist scheduled context composition; session_id=%s", session_id)


def _iso(value: datetime) -> str:
    return value.isoformat()


scheduled_agent_executor = AgentPromptExecutor()


__all__ = ["AgentPromptExecutor", "scheduled_agent_executor"]

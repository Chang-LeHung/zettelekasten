"""Agent-prompt executor for the standalone scheduler worker process."""

from collections.abc import Mapping
from datetime import datetime

from zett_agent import AgentRunConfig, ReasoningEffort, UserMessage

from ...agent.config import ZettelkastenAgentConfig
from ...agent.model_factory import create_model
from ...agent.zettelkasten import ZettelkastenAgent
from ...application.session_context import session_context_composition_service
from ...application.settings import runtime_settings_service
from ...infra.agent.runtime import get_agent_runtime_storage
from ...infra.dao import (
    model_usage_activity_storage,
    provider_storage,
    session_storage,
)
from ...infra.log import get_logger
from ...schemas import AGENT_PROMPT_ACTION_KIND, AgentPromptAction, AgentSessionCreate, JsonValue
from .contracts import ActionExecutionStatus, ActionExecutor, ActionResult, ExecutionContext

logger = get_logger(__name__)


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

        session = await session_storage.create(AgentSessionCreate(title=context.task_name))
        runtime_settings = await runtime_settings_service.get()
        model = create_model(connection)
        try:
            agent = ZettelkastenAgent(
                ZettelkastenAgentConfig(
                    session_id=session.session_id,
                    max_iterations=runtime_settings.max_turn_iterations,
                    max_asset_size_bytes=runtime_settings.max_asset_size_bytes,
                    compaction_max_tokens=runtime_settings.compaction_max_tokens,
                    compaction_keep_recent_tokens=runtime_settings.compaction_keep_recent_tokens,
                    usage_activity_storage=model_usage_activity_storage,
                    storage=get_agent_runtime_storage(),
                    context_composition_recorder=_remember_context_composition,
                    interactive=False,
                    coding_enabled=False,
                )
            )
            await agent.initialize()
            result = await agent.client(None).run(  # type: ignore[arg-type]
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

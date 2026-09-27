"""Run one non-interactive Agent prompt outside an HTTP streaming request."""

from collections.abc import Mapping

from zett_agent.agent import (
    AgentRunConfig,
)
from zett_agent.extensions.shell_approval import (
    ShellApprovalMode,
)
from zett_agent.json_types import (
    JsonValue,
)
from zett_agent.messages import (
    UserContent,
    UserMessage,
)
from zett_agent.model import (
    ReasoningEffort,
)

from ...agent.config import ZettelkastenAgentConfig
from ...agent.model_factory import create_model
from ...agent.zettelkasten import ZettelkastenAgent
from ...infra.agent.runtime import get_agent_runtime_storage
from ...infra.agent.shell_approval import shell_approval_storage
from ...infra.persistence.dao import model_usage_activity_storage, provider_storage
from ..runtime.settings import runtime_settings_service
from .session_context import session_context_composition_service


async def _remember_context_composition(session_id: str, ratios: dict[str, float]) -> None:
    """Persist context metrics from a headless IM or scheduled request."""
    await session_context_composition_service.remember(session_id, ratios)


async def run_headless_prompt(
    *,
    session_id: str,
    provider_id: str,
    request_id: str,
    message: str,
    content: UserContent | None = None,
    reasoning_effort: ReasoningEffort,
    allow_coding: bool = False,
    metadata: Mapping[str, JsonValue] | None = None,
    tags: Mapping[str, JsonValue] | None = None,
) -> str:
    """Run one complete Agent prompt and return its final text response.

    ``content`` replaces ``message`` when a caller already built ordered
    multimodal content, which is how inbound IM media reaches the model.
    """
    connection = await provider_storage.resolve_connection(provider_id)
    if connection is None:
        raise ValueError("Enabled provider not found")
    runtime_settings = await runtime_settings_service.get()
    model = create_model(connection)
    # No surface can answer a shell approval for a headless turn, and the runtime
    # waits for one without a timeout, so these sessions run their commands
    # without asking. The stored mode is what the browser shows if the session is
    # ever opened there.
    await shell_approval_storage.set_session_mode(session_id, ShellApprovalMode.ALLOW_ALL)
    try:
        agent = ZettelkastenAgent(
            ZettelkastenAgentConfig(
                session_id=session_id,
                max_iterations=runtime_settings.max_turn_iterations,
                max_asset_size_bytes=runtime_settings.max_asset_size_bytes,
                compaction_max_tokens=runtime_settings.compaction_max_tokens,
                compaction_keep_recent_tokens=runtime_settings.compaction_keep_recent_tokens,
                usage_activity_storage=model_usage_activity_storage,
                shell_approval_storage=shell_approval_storage,
                storage=get_agent_runtime_storage(),
                context_composition_recorder=_remember_context_composition,
                interactive=False,
                coding_enabled=allow_coding,
            )
        )
        await agent.initialize()
        result = await agent.client(None).run(  # type: ignore[arg-type]
            UserMessage(content=message if content is None else content),
            config=AgentRunConfig(session_id=session_id, request_id=request_id),
            model=model,
            reasoning_effort=reasoning_effort,
            metadata=dict(metadata or {}),
            tags=dict(tags or {}),
        )
        return result.content
    finally:
        await model.aclose()


__all__ = ["run_headless_prompt"]

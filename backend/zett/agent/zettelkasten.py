"""Reusable application facade around one multi-session zett-agent runtime."""

from typing import Self

from zett_agent import (
    Agent,
    AgentClient,
    AgentEventDispatcher,
    AgentRunConfig,
    AskUserExtension,
    CodingExtension,
    CompactionExtension,
    ExternalEvent,
    McpExtension,
    ModelRequestTraceExtension,
    SessionPersistenceExtension,
    ShellApprovalExtension,
    SkillExtension,
    TodoWriteExtension,
    ToolGuidelinesExtension,
    UsageActivityExtension,
)

from ..infra.agent_runtime import get_agent_runtime_storage
from .assets import AssetExtension
from .config import SYSTEM_PROMPT, ZettelkastenAgentConfig
from .context_composition import ContextCompositionExtension
from .extensions import ZettelkastenExtension
from .tags import TagExtension


class ZettelkastenAgent:
    """Own one configured conversation Agent and its request-scoped clients.

    A lightweight AgentClient is created per HTTP request so each response
    owns its own SSE dispatcher. Provider adapters remain request-scoped and
    override the optional default model without mutating this session Agent.
    """

    def __init__(self, config: ZettelkastenAgentConfig) -> None:
        self.config = config
        self.storage = config.storage or get_agent_runtime_storage()
        extensions = [
            SessionPersistenceExtension(self.storage),
            AssetExtension(max_asset_size_bytes=config.max_asset_size_bytes),
            ZettelkastenExtension(),
            TagExtension(),
            ShellApprovalExtension(config.shell_approval_storage),
            CodingExtension(),
            AskUserExtension(),
            TodoWriteExtension(),
            CompactionExtension(
                max_tokens=config.compaction_max_tokens,
                keep_recent_tokens=config.compaction_keep_recent_tokens,
            ),
            SkillExtension(config.skill_roots),
            McpExtension(
                servers=config.mcp_servers,
                config_path=config.resolved_mcp_config_path(),
                server_keys=config.mcp_server_keys,
            ),
            ToolGuidelinesExtension(),
            ContextCompositionExtension(config.context_composition_recorder),
            ModelRequestTraceExtension(),
        ]
        if config.usage_activity_storage is not None:
            extensions.append(UsageActivityExtension(config.usage_activity_storage))
        self.agent = Agent(
            None,
            system_prompt=SYSTEM_PROMPT,
            extensions=tuple(extensions),
            max_iterations=config.max_iterations,
        )

    async def initialize(self) -> Self:
        """Bind the configured session identity before the first request."""
        await self.agent.initialize(config=AgentRunConfig(session_id=self.config.session_id))
        return self

    def client(self, dispatcher: AgentEventDispatcher) -> AgentClient:
        """Bind a request-owned dispatcher to this conversation runtime."""
        return AgentClient(self.agent, event_dispatcher=dispatcher)

    def emit_external_event(self, event: ExternalEvent, *, config: AgentRunConfig) -> list[str]:
        """Route external input to extensions handling the identified request."""
        return self.agent.emit_external_event(event, config=config)

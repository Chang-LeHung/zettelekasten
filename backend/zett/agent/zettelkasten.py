"""Reusable application facade around one multi-session zett-agent runtime."""

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Self

from zett_agent import (
    Agent,
    AgentClient,
    AgentEvent,
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
from .at_command import (
    AtCommandDefinition,
    AtCommandHandler,
    AtCommandInvocation,
    AtCommandItem,
    AtCommandSource,
    named_at_commands,
)
from .config import SYSTEM_PROMPT, ZettelkastenAgentConfig
from .container import ZettelkastenContainer, ZettelkastenExt
from .extensions import (
    ArtifactExtension,
    AssetExtension,
    ContextCompositionExtension,
    SessionFilesExtension,
    TagExtension,
)
from .plugins import SessionReferenceExtension
from .slash import (
    SlashCommandDefinition,
    SlashCommandHandler,
    SlashCommandInvocation,
    stable_slash_command_id,
)

_SLASH_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_AT_COMMAND_KIND = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ZettelkastenAgent(ZettelkastenContainer):
    """Own one configured conversation Agent and its request-scoped clients.

    A lightweight AgentClient is created per HTTP request so each response
    owns its own SSE dispatcher. Provider adapters remain request-scoped and
    override the optional default model without mutating this session Agent.
    """

    def __init__(self, config: ZettelkastenAgentConfig) -> None:
        self.config = config
        self.storage = config.storage or get_agent_runtime_storage()
        self.extensions: tuple[ZettelkastenExt, ...] = (*config.resolved_extensions(), SessionReferenceExtension())
        self._extensions_loaded = False
        self._slash_commands: dict[str, SlashCommandDefinition] = {}
        self._at_commands: dict[str, AtCommandDefinition] = {}
        extensions = [
            SessionPersistenceExtension(self.storage),
            AssetExtension(max_asset_size_bytes=config.max_asset_size_bytes),
            ArtifactExtension(),
            TagExtension(),
            TodoWriteExtension(),
            CompactionExtension(
                max_tokens=config.compaction_max_tokens,
                keep_recent_tokens=config.compaction_keep_recent_tokens,
            ),
            SkillExtension(config.skill_roots),
            McpExtension(
                servers=config.mcp_servers,
                config_path=config.mcp_config_path,
                server_keys=config.mcp_server_keys,
            ),
            ToolGuidelinesExtension(),
            SessionFilesExtension(),
            ContextCompositionExtension(config.context_composition_recorder),
            ModelRequestTraceExtension(),
        ]
        if config.coding_enabled:
            extensions.extend(
                (
                    ShellApprovalExtension(config.shell_approval_storage),
                    CodingExtension(),
                )
            )
        if config.interactive:
            extensions.append(AskUserExtension())
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
        await self._load_extensions()
        await self.agent.initialize(config=AgentRunConfig(session_id=self.config.session_id))
        return self

    async def _load_extensions(self) -> None:
        """Let application extensions register their container capabilities once."""
        if self._extensions_loaded:
            return
        for extension in self.extensions:
            await extension.register(self)
        self._extensions_loaded = True

    def register_slash_command(
        self,
        *,
        owner: str,
        name: str,
        description: str,
        command_type: str,
        handler: SlashCommandHandler,
    ) -> SlashCommandDefinition:
        """Register one application slash command with a stable container ID."""
        normalized_name = name.strip()
        normalized_description = " ".join(description.split())
        normalized_type = command_type.strip()
        if not _SLASH_NAME.fullmatch(normalized_name):
            raise ValueError("Slash command names must use lowercase letters, digits, and single hyphens")
        if not normalized_description:
            raise ValueError("Slash command description cannot be empty")
        if not normalized_type:
            raise ValueError("Slash command type cannot be empty")
        command_id = stable_slash_command_id(
            owner=owner,
            command_type=normalized_type,
            name=normalized_name,
        )
        if command_id in self._slash_commands:
            raise ValueError(f"Slash command is already registered: {normalized_name}")
        command = SlashCommandDefinition(
            id=command_id,
            owner=owner,
            name=normalized_name,
            description=normalized_description,
            type=normalized_type,
            handler=handler,
        )
        self._slash_commands[command.id] = command
        return command

    def slash_commands(self) -> tuple[SlashCommandDefinition, ...]:
        """Return registered commands in deterministic display order."""
        return tuple(sorted(self._slash_commands.values(), key=lambda command: (command.name, command.id)))

    def slash_command(self, command_id: str) -> SlashCommandDefinition | None:
        """Resolve one command by the stable ID exposed to the browser."""
        return self._slash_commands.get(command_id)

    async def execute_slash_command(
        self,
        command_id: str,
        invocation: SlashCommandInvocation,
    ) -> AsyncIterator[AgentEvent]:
        """Run one registered command and yield its Agent event stream."""
        command = self.slash_command(command_id)
        if command is None:
            raise KeyError(f"Slash command not found: {command_id}")
        async for event in command.handler(invocation):
            yield event

    def register_at_command(
        self,
        *,
        owner: str,
        kind: str,
        source: AtCommandSource,
        handler: AtCommandHandler,
    ) -> AtCommandDefinition:
        """Register one kind of ``@`` referenceable resource and its Agent handoff."""
        normalized_owner = owner.strip()
        normalized_kind = kind.strip()
        if not normalized_owner:
            raise ValueError("@ command source owner cannot be empty")
        if not _AT_COMMAND_KIND.fullmatch(normalized_kind):
            raise ValueError("@ command kinds must use lowercase letters, digits, and single hyphens")
        if normalized_kind in self._at_commands:
            raise ValueError(f"@ command kind is already registered: {normalized_kind}")
        if source.owner != normalized_owner or source.kind != normalized_kind:
            raise ValueError("@ command source must describe the kind it is registered for")
        definition = AtCommandDefinition(
            owner=normalized_owner,
            kind=normalized_kind,
            source=source,
            handler=handler,
        )
        self._at_commands[definition.kind] = definition
        return definition

    def at_command_definitions(self) -> tuple[AtCommandDefinition, ...]:
        """Return registered ``@`` kinds in deterministic display order."""
        return tuple(self._at_commands[kind] for kind in sorted(self._at_commands))

    async def at_commands(self, session_id: str) -> tuple[AtCommandItem, ...]:
        """List every resource the browser may reference in this conversation.

        Sources build validated items, so listing merges what they return and
        only has to settle ``@`` token collisions between kinds.
        """
        listings = await asyncio.gather(
            *(definition.source.items(session_id) for definition in self.at_command_definitions())
        )
        return named_at_commands(item for listed in listings for item in listed)

    async def at_command(self, session_id: str, item_id: str) -> AtCommandItem | None:
        """Resolve one submitted ``@`` ID, or None when it is no longer referenceable."""
        item = next((candidate for candidate in await self.at_commands(session_id) if candidate.id == item_id), None)
        if item is None:
            return None
        if not await self._at_commands[item.kind].source.verify(session_id, item):
            return None
        return item

    async def execute_at_command(self, invocation: AtCommandInvocation) -> AsyncIterator[AgentEvent]:
        """Run the registered handler of one already-resolved ``@`` reference."""
        definition = self._at_commands.get(invocation.item.kind)
        if definition is None:
            raise KeyError(f"@ command kind is not registered: {invocation.item.kind}")
        async for event in definition.handler(invocation):
            yield event

    def client(self, dispatcher: AgentEventDispatcher) -> AgentClient:
        """Bind a request-owned dispatcher to this conversation runtime."""
        return AgentClient(self.agent, event_dispatcher=dispatcher)

    def emit_external_event(self, event: ExternalEvent, *, config: AgentRunConfig) -> list[str]:
        """Route external input to extensions handling the identified request."""
        return self.agent.emit_external_event(event, config=config)

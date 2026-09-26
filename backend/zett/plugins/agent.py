"""Contract for third-party plugins that extend the agent runtime.

Only the plugin class is Zett's own. A plugin subclasses :class:`AgentPlugin`
instead of the runtime's ``AgentExtension``, because Zett owns everything around
it: the plugin is one process-wide instance discovered from an entry point, it
declares tools instead of registering them per request, and Zett namespaces those
tools and reports its failures. Everything a hook receives or returns is the
runtime's own type — tools are ``AgentTool``, hooks take the run context, the
model request and response, a tool call, a tool result, and an exception — so a
plugin author reads one set of types rather than two parallel copies.

Plugins are third-party code: Zett enforces the boundaries it owns and reports
what a plugin did, but it never hides a plugin failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from zett_agent import (
    AgentRunContext,
    AgentTool,
    AssistantMessage,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolMessage,
)

from .contract import Plugin, PluginKind

if TYPE_CHECKING:  # annotations only: importing these here would close an import cycle
    from ..agent.at_command import AtCommandDefinition, AtCommandHandler, AtCommandSource
    from ..agent.slash import SlashCommandDefinition, SlashCommandHandler

#: Version of the agent-plugin contract Zett implements.
#:
#: A plugin declaring another version is skipped at load time, so an
#: incompatible package fails with a clear log line instead of a broken turn.
AGENT_PLUGIN_API_VERSION = 1

#: Entry-point group agent plugins are discovered through.
AGENT_PLUGIN_ENTRY_POINT_GROUP = "zett.agent"


class AgentCommandRegistry(ABC):
    """The container a plugin registers browser-facing capabilities against.

    Every capability is pinned to the plugin's own id, so a plugin cannot
    register under another owner's namespace.
    """

    @abstractmethod
    def register_slash_command(
        self,
        *,
        name: str,
        description: str,
        command_type: str,
        handler: SlashCommandHandler,
    ) -> SlashCommandDefinition:
        """Register one slash command the browser can run in this conversation."""

    @abstractmethod
    def register_at_command(
        self,
        *,
        kind: str,
        source: AtCommandSource,
        handler: AtCommandHandler,
    ) -> AtCommandDefinition:
        """Register one kind of ``@`` referenceable conversation resource.

        `zett.agent.at_command.reference_handler()` is the default handler: it
        names the referenced item and runs the turn, leaving the content to the
        tool that owns it.
        """


class AgentPlugin(Plugin, ABC):
    """One installed plugin that extends the agent runtime.

    Every hook mirrors the runtime's own lifecycle and is optional; the default
    does nothing. Two boundaries stay with Zett rather than the plugin: nothing
    here can replace the incoming user message or inject into the leading system
    prefix (that would rebuild the provider's cached prefix every turn), and no
    hook can answer an external event such as a shell approval.
    """

    kind: ClassVar[PluginKind] = PluginKind.AGENT
    api_version: ClassVar[int] = AGENT_PLUGIN_API_VERSION

    @abstractmethod
    def tools(self) -> Sequence[AgentTool]:
        """Return every tool this plugin contributes to the model.

        Names are local to the plugin: Zett registers each one as
        ``<plugin_id>__<name>``, so a plugin cannot shadow a built-in tool and
        the model always sees where a capability came from.

        The plugin owns one instance that serves concurrent conversations, so
        keep per-conversation state in the plugin's namespaced KV storage rather
        than on this object.
        """
        raise NotImplementedError

    async def before_run(self, context: AgentRunContext) -> None:
        """Run once before the first model call of a run."""

    async def after_run(self, context: AgentRunContext, answer: AssistantMessage) -> None:
        """Run once with the final assistant answer of a successful run."""

    async def on_success(self, context: AgentRunContext, answer: AssistantMessage) -> None:
        """Run after every ``after_run`` hook of a successful run."""

    async def on_error(self, context: AgentRunContext, error: Exception) -> None:
        """Run before a failure is returned to the caller."""

    async def before_turn(self, context: AgentRunContext) -> None:
        """Run before one model step and the tool calls it requests."""

    async def after_turn(self, context: AgentRunContext) -> None:
        """Run after one model step and its tool calls finished."""

    async def before_model(self, context: AgentRunContext, request: ModelRequest) -> None:
        """Inspect the request about to be sent to the provider."""

    async def after_model(self, context: AgentRunContext, response: ModelResponse) -> None:
        """Inspect the assistant message the provider just produced."""

    async def before_tool(self, context: AgentRunContext, call: ToolCall) -> None:
        """Inspect one tool invocation before it executes."""

    async def after_tool(
        self,
        context: AgentRunContext,
        call: ToolCall,
        result: ToolMessage,
        error: Exception | None,
    ) -> None:
        """Inspect one tool outcome, including a failed one."""

    async def register(self, registry: AgentCommandRegistry) -> None:
        """Register slash commands and ``@`` kinds; the default registers none.

        Capabilities registered here reach the browser through the same
        endpoints the built-in ones use, so a plugin adds a command by
        implementing a handler rather than by touching Zett's HTTP layer. A
        plugin that only needs the model to learn what the user pointed at can
        pass `zett.agent.at_command.reference_handler()` as its ``@`` handler.
        """

    async def start(self) -> None:
        """Prepare process-wide resources; the default owns nothing."""

    async def stop(self) -> None:
        """Release what :meth:`start` opened; the default owns nothing."""


__all__ = [
    "AGENT_PLUGIN_API_VERSION",
    "AGENT_PLUGIN_ENTRY_POINT_GROUP",
    "AgentCommandRegistry",
    "AgentPlugin",
]

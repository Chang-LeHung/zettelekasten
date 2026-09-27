"""Keep optional tools behind tool search only where the protocol can search them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import replace

from zett_agent.agent import (
    AgentRunContext,
)
from zett_agent.extensions.base import (
    AgentExtension,
    ModelRequestNext,
)
from zett_agent.extensions.tool_search import (
    ToolSearchExtension,
)
from zett_agent.messages import (
    SystemMessage,
)
from zett_agent.model import (
    ModelEvent,
    ModelRequest,
    ToolDefinition,
)

from ..model_factory import uses_responses_api


class DeferredToolExtension(AgentExtension):
    """Own the deferred-tool contract for every provider protocol.

    The Responses API hides a deferred definition and hands it to the model only
    after ``tool_search`` selects it, so a Responses run registers zett-agent's
    search tool and leaves the flags alone. Chat Completions, Anthropic, Google,
    and Ollama cannot answer client-side tool search and reject a search tool, so
    there every definition is offered as an ordinary function instead: the
    request is rewritten with ``deferred=False`` and no search tool is registered.

    Priority keeps this rewrite ahead of every extension that filters deferred
    definitions, such as zett-agent's ``ToolSearchExtension``: a later filter must
    see the definitions this protocol actually offers, or it would strip tools
    this extension just revealed.
    """

    #: Lower numbers run first, and the default group runs at 100.
    priority = 90

    def __init__(self, search: ToolSearchExtension | None = None) -> None:
        self._search = search or ToolSearchExtension()

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register the request-scoped search tool for a Responses API run only."""
        if uses_responses_api(context.model):
            await self._search.on_tool(context)

    async def on_state(self, context: AgentRunContext) -> None:
        """Name the searchable capabilities, but only where search exists."""
        if not uses_responses_api(context.model):
            return
        message = SystemMessage(content=_SEARCH_INSTRUCTIONS)
        instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
        context.add_message(message, index=len(instructions))

    async def on_model_request(
        self,
        context: AgentRunContext,
        request: ModelRequest,
        call_next: ModelRequestNext,
    ) -> AsyncIterator[ModelEvent]:
        """Send the definitions this protocol can actually serve."""
        tools = self._tools_for(request, search=uses_responses_api(context.model))
        async with aclosing(call_next(replace(request, tools=tools))) as events:
            async for event in events:
                yield event

    @staticmethod
    def _tools_for(request: ModelRequest, *, search: bool) -> tuple[ToolDefinition, ...]:
        """Return the definitions one model request may carry.

        Only the search tool's registration is delegated to zett-agent, so this
        extension owns both halves of the contract: hiding the deferred
        definitions the Responses API loads through search, and revealing them
        again for a protocol that cannot search.
        """
        if search:
            return tuple(tool for tool in request.tools if not tool.deferred)
        return tuple(
            replace(tool, deferred=False)
            for tool in request.tools
            # Such a protocol rejects the definition that answers client-side
            # search, so it must never reach the provider either.
            if not tool.local_tool_search
        )


__all__ = ["DeferredToolExtension"]

#: Fixed text, so it extends the prompt-cache prefix instead of rebuilding it.
_SEARCH_INSTRUCTIONS = (
    "# Tool search\n"
    "Tools that a conversation rarely needs are not listed with your tool definitions; load them on demand.\n"
    "Call tool_search with short keyword queries when a task needs one of them.\n"
    "The deferred set currently covers scheduled tasks (create, list, read, update, disable) and the "
    "provider list a scheduled task must reference."
)

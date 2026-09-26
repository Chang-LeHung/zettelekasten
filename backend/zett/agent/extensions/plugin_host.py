"""Zett's adapter between the agent runtime and installed agent plugins.

This is the only extension a plugin's code reaches the runtime through. It
forwards the runtime's own objects to each plugin in installation order and
keeps the two boundaries Zett owns:

* Tools are registered as ``<plugin_id>__<tool>``, so a plugin can never shadow
  a built-in tool.
* A failing hook becomes a :class:`~zett.plugins.PluginError` naming the plugin
  and the hook. The run fails visibly instead of continuing with a plugin that
  silently stopped working.
* Plugins never see ``ask_user_response`` or ``shell_approval_response``: the
  adapter keeps the runtime's default that accepts no external event.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from typing import Any

from zett_agent import (
    AgentExtension,
    AgentRunContext,
    AgentTool,
    AssistantMessage,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolMessage,
)

from ...infra.log import get_logger
from ...plugins import AgentPlugin, PluginError

logger = get_logger(__name__)


class AgentPluginExtension(AgentExtension):
    """Call every installed agent plugin from inside one runtime extension."""

    def __init__(self, plugins: Sequence[AgentPlugin]) -> None:
        self.plugins = tuple(plugins)
        self.name = "AgentPluginExtension"

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register every plugin tool under its plugin's namespace."""
        for plugin in self.plugins:
            tools = await self._call(plugin, "tools", _declared_tools, plugin)
            for tool in tools:
                await self._call(plugin, f"tool {tool.name!r}", _register_tool, context, plugin.plugin_id, tool)

    async def before_run(self, context: AgentRunContext) -> None:
        await self._forward("before_run", context)

    async def after_run(self, context: AgentRunContext, result: AssistantMessage) -> None:
        await self._forward("after_run", context, result)

    async def on_success(self, context: AgentRunContext, result: AssistantMessage) -> None:
        await self._forward("on_success", context, result)

    async def on_error(self, context: AgentRunContext, error: Exception) -> None:
        await self._forward("on_error", context, error)

    async def before_turn(self, context: AgentRunContext) -> None:
        await self._forward("before_turn", context)

    async def after_turn(self, context: AgentRunContext) -> None:
        await self._forward("after_turn", context)

    async def before_model(self, context: AgentRunContext, request: ModelRequest) -> None:
        await self._forward("before_model", context, request)

    async def after_model(self, context: AgentRunContext, response: ModelResponse) -> None:
        await self._forward("after_model", context, response)

    async def before_tool(self, context: AgentRunContext, call: ToolCall) -> None:
        await self._forward("before_tool", context, call)

    async def after_tool(
        self,
        context: AgentRunContext,
        call: ToolCall,
        result: ToolMessage,
        error: Exception | None,
    ) -> None:
        await self._forward("after_tool", context, call, result, error)

    async def _forward(self, hook: str, *args: Any) -> None:
        """Call one hook on every plugin, in installation order."""
        for plugin in self.plugins:
            await self._call(plugin, hook, getattr(plugin, hook), *args)

    async def _call(self, plugin: AgentPlugin, scope: str, callback: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """Run one plugin call, naming the plugin when it fails."""
        try:
            return await callback(*args)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise _failure(plugin.plugin_id, scope, error) from error


async def _declared_tools(plugin: AgentPlugin) -> tuple[AgentTool, ...]:
    """Read one plugin's tool declarations."""
    return tuple(plugin.tools())


async def _register_tool(context: AgentRunContext, plugin_id: str, tool: AgentTool) -> None:
    """Register one plugin tool as ``<plugin_id>__<name>``."""
    context.register_tool(replace(tool, name=f"{plugin_id}__{tool.name}"))


def _failure(plugin_id: str, scope: str, error: Exception) -> PluginError:
    """Report one failed plugin call with the plugin, scope, and message."""
    logger.exception("Agent plugin failed; plugin_id=%s scope=%s", plugin_id, scope)
    return PluginError(f"Agent plugin {plugin_id!r} failed in {scope}: {error}")


__all__ = ["AgentPluginExtension"]

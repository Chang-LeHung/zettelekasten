"""Container capabilities contributed by installed agent plugins.

An agent plugin registers slash commands and ``@`` reference kinds through the
same container interface Zett's own plugins use. This adapter is what it talks
to: every call is pinned to the plugin's own owner id, so a plugin cannot
register under another owner's namespace or collide with a built-in.
"""

from __future__ import annotations

from ...plugins import AgentCommandRegistry
from ..at_command import AtCommandDefinition, AtCommandHandler, AtCommandSource
from ..container import ZettelkastenContainer
from ..slash import SlashCommandDefinition, SlashCommandHandler


class PluginCommandRegistry(AgentCommandRegistry):
    """Register one plugin's capabilities under that plugin's owner id."""

    def __init__(self, container: ZettelkastenContainer, plugin_id: str) -> None:
        self._container = container
        self._plugin_id = plugin_id

    def register_slash_command(
        self,
        *,
        name: str,
        description: str,
        command_type: str,
        handler: SlashCommandHandler,
    ) -> SlashCommandDefinition:
        """Register one slash command owned by this plugin."""
        return self._container.register_slash_command(
            owner=self._plugin_id,
            name=name,
            description=description,
            command_type=command_type,
            handler=handler,
        )

    def register_at_command(
        self,
        *,
        kind: str,
        source: AtCommandSource,
        handler: AtCommandHandler,
    ) -> AtCommandDefinition:
        """Register one ``@`` reference kind owned by this plugin."""
        return self._container.register_at_command(
            owner=self._plugin_id,
            kind=kind,
            source=source,
            handler=handler,
        )


__all__ = ["PluginCommandRegistry"]

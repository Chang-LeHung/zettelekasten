"""Abstract container interface that Zettelkasten extensions register against.

The container is the whole capability surface an extension sees: it registers
slash commands and ``@`` commands. ``ZettelkastenAgent`` is the concrete
implementation, while extensions depend only on this interface, so neither side
needs to know the other's internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .at_command import (
        AtCommandDefinition,
        AtCommandHandler,
        AtCommandSource,
    )
    from .slash import SlashCommandDefinition, SlashCommandHandler


class ZettelkastenExt(ABC):
    """One application extension loaded and registered by the container."""

    name: str

    @abstractmethod
    async def register(self, container: ZettelkastenContainer) -> None:
        """Register tools, slash commands, and ``@`` commands on the container."""
        raise NotImplementedError


class ZettelkastenContainer(ABC):
    """Capabilities one extension may use on the container that loaded it."""

    @abstractmethod
    def register_slash_command(
        self,
        *,
        owner: str,
        name: str,
        description: str,
        command_type: str,
        handler: SlashCommandHandler,
    ) -> SlashCommandDefinition:
        """Register one slash command and return its stable definition."""
        raise NotImplementedError

    @abstractmethod
    def register_at_command(
        self,
        *,
        owner: str,
        kind: str,
        source: AtCommandSource,
        handler: AtCommandHandler,
    ) -> AtCommandDefinition:
        """Register one referenceable resource kind and its Agent handoff."""
        raise NotImplementedError


__all__ = ["ZettelkastenContainer", "ZettelkastenExt"]

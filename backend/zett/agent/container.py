"""Abstract container interface that Zettelkasten extensions register against.

The container is the whole capability surface an extension sees: it registers
slash commands and ``@`` commands, and it streams one prepared turn through the
Agent. ``ZettelkastenAgent`` is the concrete implementation, while extensions
depend only on this interface, so neither side needs to know the other's
internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from zett_agent import AgentEvent, UserMessage

if TYPE_CHECKING:
    from .at_command import (
        AtCommandDefinition,
        AtCommandHandler,
        AtCommandSource,
    )
    from .slash import CommandInvocation, SlashCommandDefinition, SlashCommandHandler


class ZettelkastenExt(ABC):
    """One application extension loaded and registered by the container."""

    name: str

    @abstractmethod
    async def register(self, container: ZettelkastenContainer) -> None:
        """Register tools, slash commands, and ``@`` commands on the container."""
        raise NotImplementedError


class ZettelkastenContainer(ABC):
    """Capabilities one extension may use on the container that loaded it.

    Extensions only register capabilities here. Running a command or reference is
    the container's job, and it hands the prepared turn to the Agent through
    :meth:`stream_to_agent`.
    """

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

    @abstractmethod
    def stream_to_agent(
        self,
        invocation: CommandInvocation,
        *,
        message: UserMessage | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Stream one prepared command or reference turn through the Agent.

        Implementations are async generators. Supplying ``message`` replaces the
        browser message the invocation carried, which is how a skill command or
        an ``@`` reference names what the model must read.
        """
        raise NotImplementedError


__all__ = ["ZettelkastenContainer", "ZettelkastenExt"]

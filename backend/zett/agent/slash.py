"""Container-level slash command registration and execution contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from uuid import UUID, uuid5

from zett_agent import AgentEvent

from .._compat import TypeAliasType
from ..application.agent.turns import AgentTurn

SLASH_COMMAND_NAMESPACE = UUID("3c9d2c8b-9f14-51a9-a759-a8c9a3bf4f8a")


@dataclass(slots=True)
class SlashCommandInvocation(AgentTurn):
    """One prepared turn that a slash command may rewrite before it runs."""


@dataclass(frozen=True, slots=True)
class SlashCommandDefinition:
    """Registered slash command metadata and its Agent stream handler."""

    id: str
    owner: str
    name: str
    description: str
    type: str
    handler: SlashCommandHandler


@dataclass(frozen=True, slots=True)
class SlashCommandRegistration:
    """Arguments supplied by one extension when registering a command."""

    name: str
    description: str
    type: str
    handler: SlashCommandHandler


SlashCommandHandler = TypeAliasType(
    "SlashCommandHandler", Callable[[SlashCommandInvocation], AsyncIterator[AgentEvent]]
)


def stable_slash_command_id(*, owner: str, command_type: str, name: str) -> str:
    """Generate an ID that remains valid across request-scoped containers."""
    return str(uuid5(SLASH_COMMAND_NAMESPACE, f"{owner}:{command_type}:{name}"))


__all__ = [
    "SLASH_COMMAND_NAMESPACE",
    "SlashCommandDefinition",
    "SlashCommandHandler",
    "SlashCommandInvocation",
    "SlashCommandRegistration",
    "stable_slash_command_id",
]

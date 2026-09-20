"""Container-level slash command registration and execution contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

from zett_agent import (
    AgentClient,
    AgentEvent,
    AgentModel,
    AgentRunConfig,
    JsonValue,
    ReasoningEffort,
    UserMessage,
)

# The container interface lives in ``container.py``; it is imported here only so
# the handler alias below names the same type extensions register against.
from .at_command import AtCommandInvocation
from .container import ZettelkastenContainer

SLASH_COMMAND_NAMESPACE = UUID("3c9d2c8b-9f14-51a9-a759-a8c9a3bf4f8a")


@dataclass(frozen=True, slots=True)
class SlashCommandInvocation:
    """One prepared Agent request that a slash command may send to the model."""

    session_id: str
    client: AgentClient
    message: UserMessage
    model: AgentModel
    config: AgentRunConfig
    reasoning_effort: ReasoningEffort
    metadata: Mapping[str, JsonValue]
    tags: Mapping[str, JsonValue]


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


type SlashCommandHandler = Callable[
    ["ZettelkastenContainer", SlashCommandInvocation],
    AsyncIterator[AgentEvent],
]
type CommandInvocation = SlashCommandInvocation | AtCommandInvocation


def stable_slash_command_id(*, owner: str, command_type: str, name: str) -> str:
    """Generate an ID that remains valid across request-scoped containers."""
    return str(uuid5(SLASH_COMMAND_NAMESPACE, f"{owner}:{command_type}:{name}"))


__all__ = [
    "SLASH_COMMAND_NAMESPACE",
    "CommandInvocation",
    "SlashCommandDefinition",
    "SlashCommandHandler",
    "SlashCommandInvocation",
    "SlashCommandRegistration",
    "stable_slash_command_id",
]

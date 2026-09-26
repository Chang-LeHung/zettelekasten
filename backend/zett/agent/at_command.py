"""Container-level ``@`` reference capability and its Agent handoff.

A slash command selects one capability for a turn. An ``@`` command selects one
resource that already belongs to the conversation, and a turn may reference
several of them inside ordinary text. Both are container capabilities: an
extension registers an :class:`AtCommandSource` for one kind of resource, the
container assigns stable IDs and unique token names, and the browser submits the
IDs it resolved from its own text.

One turn receives the kind and ID of exactly what the user referenced; the model
reads content through the existing ``get_asset`` and ``get_artifact`` tools. No
session snapshot and no content preview is injected, so nothing here grows the
leading system prefix or pays for context the user did not point at.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid5

from zett_agent import (
    AgentEvent,
    ImageContent,
    TextContent,
    UserContentPart,
    UserMessage,
)

from .._compat import TypeAliasType
from ..application.agent.turns import AgentTurn
from ..messages import MessagePartCodec

AT_COMMAND_NAMESPACE = UUID("7f0b0be6-9d3f-5a3f-8f1e-1b7f2f6c4a11")
AT_COMMAND_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_MAX_TOKEN_CHARS = 48
_MAX_DESCRIPTION_CHARS = 160
_CODEC = MessagePartCodec()


@dataclass(frozen=True, slots=True)
class AtCommandItem:
    """One conversation resource the browser can reference with an ``@`` token.

    The container never re-validates listed items: a source builds them through
    :meth:`AtCommandSource.item`, and this constructor rejects anything that
    could not render in the reference menu.
    """

    id: str
    kind: str
    name: str
    label: str
    description: str
    target_id: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("@ command items require an ID")
        if not AT_COMMAND_NAME.fullmatch(self.kind):
            raise ValueError("@ command kinds must use lowercase letters, digits, and single hyphens")
        if not AT_COMMAND_NAME.fullmatch(self.name):
            raise ValueError("@ command names must use lowercase letters, digits, and single hyphens")
        if not self.label.strip():
            raise ValueError("@ command items require a label")
        if not self.description.strip():
            raise ValueError("@ command items require a description")
        if not self.target_id:
            raise ValueError("@ command items require a target ID")

    def recorded(self) -> dict[str, str]:
        """Return the browser-safe record stored beside one referenced turn."""
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "label": self.label,
            "target_id": self.target_id,
        }


@dataclass(slots=True)
class AtCommandInvocation(AgentTurn):
    """One prepared turn that references a conversation resource."""

    item: AtCommandItem


@dataclass(frozen=True, slots=True)
class AtCommandDefinition:
    """One registered ``@`` kind: its listing source and Agent-stream handler."""

    owner: str
    kind: str
    source: AtCommandSource
    handler: AtCommandHandler


AtCommandHandler = TypeAliasType("AtCommandHandler", Callable[[AtCommandInvocation], AsyncIterator[AgentEvent]])


class AtCommandSource(ABC):
    """One container-registered provider of mentionable conversation resources.

    ``items`` lists what the current session may reference. ``verify`` confirms
    one listed item is still readable before its ID is handed to the model, which
    covers resources deleted between listing and sending.
    """

    #: Extension that owns this source; it also namespaces the stable item IDs.
    owner: str
    #: Unique resource kind, such as ``asset`` or ``artifact``.
    kind: str

    def item(
        self,
        *,
        target_id: str,
        label: str,
        description: str,
        name: str | None = None,
    ) -> AtCommandItem:
        """Build one listed item of this source's kind.

        Sources describe a resource; identity, token name, and menu text are
        derived here so every kind stamps them the same way.
        """
        return AtCommandItem(
            id=stable_at_command_id(owner=self.owner, kind=self.kind, target_id=target_id),
            kind=self.kind,
            name=at_command_token_name(name or label, fallback=self.kind),
            label=label.strip(),
            description=at_command_description(description),
            target_id=target_id,
        )

    @abstractmethod
    async def items(self, session_id: str) -> Sequence[AtCommandItem]:
        """List the referenceable resources of one conversation."""
        raise NotImplementedError

    @abstractmethod
    async def verify(self, session_id: str, item: AtCommandItem) -> bool:
        """Return whether one already-listed item still exists."""
        raise NotImplementedError


def stable_at_command_id(*, owner: str, kind: str, target_id: str) -> str:
    """Generate an ID that survives container recreation for one target."""
    return str(uuid5(AT_COMMAND_NAMESPACE, f"{owner}:{kind}:{target_id}"))


def at_command_token_name(label: str, *, fallback: str) -> str:
    """Slug one display label into a valid ``@`` token name."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.strip().lower())[:_MAX_TOKEN_CHARS].strip("-")
    return slug or fallback


def named_at_commands(items: Iterable[AtCommandItem]) -> tuple[AtCommandItem, ...]:
    """Give one listed session deterministic, unique ``@`` names.

    Items already carry normalized names; only a collision between two kinds
    needs the numeric suffix.
    """
    ordered = sorted(items, key=lambda item: (item.kind, item.label.casefold(), item.target_id))
    used: set[str] = set()
    named: list[AtCommandItem] = []
    for item in ordered:
        name = item.name
        suffix = 2
        while name in used:
            name = f"{item.name}-{suffix}"
            suffix += 1
        used.add(name)
        named.append(replace(item, name=name))
    return tuple(named)


def at_command_message(message: UserMessage, items: Sequence[AtCommandItem]) -> UserMessage:
    """Return the Agent message for one turn that references conversation resources.

    Every reference contributes one line naming its kind and ID, followed by the
    user's own words, so the ``@`` tokens stay meaningful in the request and the
    model decides what to read. Images the browser already sent keep their order.
    ``attributes`` records the browser message so the conversation UI can render
    what the user typed instead of the expanded prompt.
    """
    if not items:
        return message
    lines = "\n".join(f"- @{item.name}: {item.kind} {item.target_id}" for item in items)
    header = (
        "The user referenced resources from this conversation with @ tokens. "
        "Their content is not included: read what you need with the matching tool.\n\n"
        f"{lines}\n\n"
        "User request:\n"
    )
    parts: list[UserContentPart] = [TextContent(f"{header}{message.text}")]
    parts.extend(part for part in message.parts if isinstance(part, ImageContent))
    attributes: dict[str, Any] = dict(message.attributes)
    attributes["at_command"] = {
        "references": [item.recorded() for item in items],
        "raw_parts": [part.model_dump() for part in _CODEC.to_front_parts(message.parts)],
    }
    return UserMessage(content=parts, attributes=attributes)


def reference_handler() -> AtCommandHandler:
    """Build the default handler for one registered ``@`` kind.

    Most kinds only need the model to learn what the user pointed at, so this
    handler names each reference and runs the turn: the content stays behind the
    tool that owns it (``get_asset``, ``get_artifact``, or a plugin's own tool),
    and the Raw Log records the browser message so the conversation UI shows what
    the user typed instead of the expanded prompt.
    """

    async def handler(invocation: AtCommandInvocation) -> AsyncIterator[AgentEvent]:
        message = at_command_message(invocation.message, (invocation.item,))
        async for event in invocation.prompt(message=message):
            yield event

    return handler


def at_command_description(value: str) -> str:
    """Normalize one user-visible menu description."""
    collapsed = " ".join(value.split())
    if len(collapsed) <= _MAX_DESCRIPTION_CHARS:
        return collapsed
    return f"{collapsed[: _MAX_DESCRIPTION_CHARS - 1].rstrip()}…"


__all__ = [
    "AT_COMMAND_NAME",
    "AT_COMMAND_NAMESPACE",
    "AtCommandDefinition",
    "AtCommandHandler",
    "AtCommandItem",
    "AtCommandInvocation",
    "AtCommandSource",
    "at_command_description",
    "at_command_message",
    "at_command_token_name",
    "named_at_commands",
    "reference_handler",
    "stable_at_command_id",
]

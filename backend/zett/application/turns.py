"""One prepared turn and the single model call it is allowed to make.

The HTTP message route, slash command handlers, and ``@`` reference handlers all
describe their turn as an :class:`AgentTurn` and call :meth:`AgentTurn.prompt`.
Run options are therefore assembled once, and a handler only decides which
message the model must read.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field

from zett_agent import (
    AgentClient,
    AgentEvent,
    AgentModel,
    AgentRunConfig,
    JsonValue,
    ReasoningEffort,
    UserMessage,
)


class TurnAlreadyPromptedError(RuntimeError):
    """Raised when one prepared turn tries to reach the model a second time."""


@dataclass(slots=True)
class AgentTurn:
    """One prepared user turn and the request-owned client that runs it.

    A turn is single use: it holds the client of one reserved request, so a
    second prompt would start a competing model request for the same reservation.
    """

    session_id: str
    client: AgentClient
    message: UserMessage
    model: AgentModel
    config: AgentRunConfig
    reasoning_effort: ReasoningEffort
    metadata: Mapping[str, JsonValue]
    tags: Mapping[str, JsonValue]
    #: Set by prompt() so one prepared turn can never run the model twice.
    _prompted: bool = field(default=False, init=False, repr=False, compare=False)

    def prompt(self, message: UserMessage | None = None) -> AsyncIterator[AgentEvent]:
        """Stream this turn through its request-owned client, exactly once.

        Args:
            message: Optional replacement for the message the turn carried, which
                is how a skill command or an ``@`` reference names what the model
                must read.

        Raises:
            TurnAlreadyPromptedError: The turn already started a model request.
        """
        if self._prompted:
            raise TurnAlreadyPromptedError(f"Turn for session {self.session_id} was already prompted")
        self._prompted = True
        return self.client.stream(
            self.message if message is None else message,
            config=self.config,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            metadata=self.metadata,
            tags=self.tags,
        )


__all__ = ["AgentTurn", "TurnAlreadyPromptedError"]

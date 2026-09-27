"""The single-use model call of one prepared turn."""

from collections.abc import AsyncIterator

import pytest
from zett_agent.agent import (
    AgentRunConfig,
)
from zett_agent.events import (
    AgentEvent,
    AgentEventType,
)
from zett_agent.messages import (
    UserMessage,
)
from zett_agent.model import (
    ReasoningEffort,
)

from zett.application.agent.turns import AgentTurn, TurnAlreadyPromptedError


class RecordingClient:
    """Record the prompt a turn sends instead of running a model."""

    def __init__(self, events: list[AgentEvent]) -> None:
        self.calls: list[dict[str, object]] = []
        self._events = events

    async def stream(self, message: UserMessage, **options: object) -> AsyncIterator[AgentEvent]:
        self.calls.append({"message": message, **options})
        for event in self._events:
            yield event


def _turn(client: RecordingClient) -> AgentTurn:
    return AgentTurn(
        session_id="session",
        client=client,  # type: ignore[arg-type]
        message=UserMessage(content="original"),
        model=None,  # type: ignore[arg-type]
        config=AgentRunConfig(session_id="session"),
        reasoning_effort=ReasoningEffort.MEDIUM,
        metadata={"request": "one"},
        tags={"kind": "test"},
    )


async def test_prompt_streams_the_turn_through_its_client() -> None:
    event = AgentEvent(AgentEventType.CUSTOM, session_id="session", name="probe")
    client = RecordingClient([event])
    turn = _turn(client)

    events = [item async for item in turn.prompt()]

    assert events == [event]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert isinstance(call["message"], UserMessage)
    assert call["message"].text == "original"
    assert call["reasoning_effort"] is ReasoningEffort.MEDIUM
    assert call["metadata"] == {"request": "one"}
    assert call["tags"] == {"kind": "test"}


async def test_prompt_can_replace_the_message_it_carries() -> None:
    client = RecordingClient([])
    turn = _turn(client)

    [item async for item in turn.prompt(message=UserMessage(content="rewritten"))]

    replacement = client.calls[0]["message"]
    assert isinstance(replacement, UserMessage)
    assert replacement.text == "rewritten"
    assert turn.message.text == "original"


async def test_one_turn_cannot_prompt_the_model_twice() -> None:
    client = RecordingClient([])
    turn = _turn(client)

    [item async for item in turn.prompt()]

    with pytest.raises(TurnAlreadyPromptedError, match="already prompted"):
        turn.prompt()
    assert len(client.calls) == 1

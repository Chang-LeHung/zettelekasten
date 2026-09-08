"""SSE projection and minimal zett-agent composition tests."""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from zett_agent import (
    AgentConfig,
    AgentEvent,
    AgentEventType,
    AssistantMessage,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ToolCall,
    ToolMessage,
)

from zett.agent import ZettelkastenAgent, ZettelkastenEventDispatcher, event_payload


class StreamingModel:
    """Produce deterministic reasoning and text without external I/O."""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        assert request.messages[-1].text == "Hello"
        yield ModelEvent.reasoning("Think")
        yield ModelEvent.text("Hi")
        yield ModelEvent.completed(
            ModelResponse(
                AssistantMessage(content="Hi", reasoning="Think", provider="test", model="test-model"),
                finish_reason="stop",
                usage=ModelUsage(input_tokens=5, output_tokens=2, reasoning_tokens=1),
            )
        )


def decode_frame(frame: str) -> tuple[str, dict[str, object]]:
    """Decode the strict two-line JSON frame emitted by the dispatcher."""
    event_line, data_line = frame.strip().splitlines()
    return event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))


async def test_agent_uses_create_agent_and_sends_ordered_sse_frames():
    frames: list[str] = []
    tasks: list[asyncio.Task[object] | None] = []

    async def send(frame: str) -> None:
        tasks.append(asyncio.current_task())
        frames.append(frame)

    owner = asyncio.current_task()
    agent = await ZettelkastenAgent.create(
        StreamingModel(),
        send=send,
        config=AgentConfig(session_id="session-1"),
    )
    events = [event async for event in agent.stream("Hello")]
    decoded = [decode_frame(frame) for frame in frames]

    assert [name for name, _ in decoded] == [event.type.value for event in events]
    assert all(task is owner for task in tasks)
    reasoning = next(payload for name, payload in decoded if name == "reasoning_delta")
    content = next(payload for name, payload in decoded if name == "text_delta")
    completed = next(payload for name, payload in decoded if name == "model_completed")
    assert reasoning == {"session_id": "session-1", "phase": "generating", "delta": "Think"}
    assert content == {"session_id": "session-1", "phase": "generating", "delta": "Hi"}
    assert completed["usage"] == {
        "input_tokens": 5,
        "output_tokens": 2,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 1,
    }


async def test_run_returns_answer_after_all_frames_are_sent():
    frames = []

    async def send(frame: str) -> None:
        frames.append(decode_frame(frame)[0])

    agent = await ZettelkastenAgent.create(StreamingModel(), send=send)
    answer = await agent.run("Hello")
    assert answer.content == "Hi"
    assert frames[-1] == AgentEventType.RUN_COMPLETED.value


async def test_send_failure_propagates_and_stops_the_agent_stream():
    calls = 0

    async def send(_: str) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("SSE disconnected")

    agent = await ZettelkastenAgent.create(StreamingModel(), send=send)
    with pytest.raises(RuntimeError, match="SSE disconnected"):
        await agent.run("Hello")
    assert calls == 1


@pytest.mark.parametrize(
    ("content", "expected"),
    [('{"saved":true}', {"saved": True}), ("plain output", "plain output"), ("", "")],
)
def test_tool_results_are_forwarded_without_tool_specific_logic(content, expected):
    call = ToolCall("call-1", "any_tool", {"path": "notes.md"})
    message = ToolMessage(content=content, tool_call_id=call.id, name=call.name, success=True)
    payload = event_payload(
        AgentEvent(
            AgentEventType.TOOL_COMPLETED,
            session_id="session-1",
            tool_calls=[call],
            message=message,
        )
    )
    assert payload["tool_calls"] == [{"id": "call-1", "name": "any_tool", "arguments": {"path": "notes.md"}}]
    assert payload["message"] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "name": "any_tool",
        "success": True,
        "output": expected,
        "attributes": {},
    }


async def test_custom_event_keeps_name_and_payload_namespaces():
    frames = []

    async def send(frame: str) -> None:
        frames.append(decode_frame(frame))

    dispatcher = ZettelkastenEventDispatcher(send)
    await dispatcher.dispatch(
        AgentEvent(
            AgentEventType.CUSTOM,
            session_id="session-1",
            name="ask_user",
            payload={"question": "Continue?"},
        )
    )
    assert frames == [
        (
            "custom",
            {
                "session_id": "session-1",
                "phase": None,
                "name": "ask_user",
                "payload": {"question": "Continue?"},
            },
        )
    ]

"""The agent's model-request and tool-call log lines."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from zett_agent import (
    AgentRunConfig,
    ImageBytesSource,
    ImageContent,
    ModelEvent,
    ModelRequest,
    ToolCall,
    UserMessage,
)

from zett.agent.extensions import TraceLogExtension


def _context() -> SimpleNamespace:
    """Minimal stand-in for the run context the hooks read their ids from."""
    return SimpleNamespace(config=AgentRunConfig(session_id="session-1", request_id="request-1"))


async def _stream(request: ModelRequest) -> AsyncIterator[ModelEvent]:
    del request
    yield ModelEvent.text("hello")
    yield ModelEvent.text("!")
    yield ModelEvent.completed(None)


async def test_model_request_is_logged_before_and_after(captured_logs) -> None:
    extension = TraceLogExtension()
    events = [
        event
        async for event in extension.on_model_request(
            _context(),
            ModelRequest(messages=[UserMessage(content="hi")]),
            _stream,
        )
    ]

    assert len(events) == 3
    assert any(
        "Model request" in message
        and "session_id=session-1" in message
        and "messages=1" in message
        and "last=user:'hi'" in message
        for message in captured_logs
    )
    assert any(
        "Model response" in message
        and "request_id=request-1" in message
        and "chars=6" in message
        and "text='hello!'" in message
        for message in captured_logs
    )


async def test_model_response_preview_is_capped(captured_logs) -> None:
    async def long_stream(request: ModelRequest) -> AsyncIterator[ModelEvent]:
        del request
        yield ModelEvent.text("z" * 400)
        yield ModelEvent.completed(None)

    async for _ in TraceLogExtension().on_model_request(
        _context(), ModelRequest(messages=[UserMessage(content="hi")]), long_stream
    ):
        pass

    response = next(message for message in captured_logs if "Model response" in message)
    assert "chars=400" in response
    text = response.split("text=", 1)[1]
    assert text == f"'{'z' * 60}…'"


async def test_model_request_previews_an_image_message_without_its_bytes(captured_logs) -> None:
    image = ImageContent(source=ImageBytesSource(data=b"png-bytes", media_type="image/png"))

    async for _ in TraceLogExtension().on_model_request(
        _context(),
        ModelRequest(messages=[UserMessage(content=[image])]),
        _stream,
    ):
        pass

    request = next(message for message in captured_logs if "Model request" in message)
    assert "last=user:'<image>'" in request
    assert "png-bytes" not in request


async def test_model_request_failure_is_logged_and_reraised(captured_logs) -> None:
    async def failing(request: ModelRequest) -> AsyncIterator[ModelEvent]:
        del request
        raise RuntimeError("provider exploded")
        yield ModelEvent.text("never")  # pragma: no cover - unreachable by design

    with pytest.raises(RuntimeError):
        async for _ in TraceLogExtension().on_model_request(
            _context(), ModelRequest(messages=[UserMessage(content="hi")]), failing
        ):
            pass  # pragma: no cover - the stream raises before yielding

    assert any("Model request failed" in message and "provider exploded" in message for message in captured_logs)


async def test_tool_call_is_logged_with_capped_arguments_and_result(captured_logs) -> None:
    async def call_next() -> str:
        return "y" * 400

    result = await TraceLogExtension().on_tool_call(
        _context(),
        ToolCall("call-1", "create_artifact", {"content": "x" * 400}),
        call_next,
    )

    assert result == "y" * 400
    started = next(message for message in captured_logs if "Tool call;" in message)
    assert "tool=create_artifact" in started
    arguments = started.split("args=", 1)[1]
    assert arguments.endswith("…") and len(arguments) == 61
    assert "x" * 61 not in started
    completed = next(message for message in captured_logs if "Tool call completed" in message)
    assert f"result={'y' * 60}…" in completed
    assert "y" * 61 not in completed


async def test_tool_call_failure_is_logged_and_reraised(captured_logs) -> None:
    async def call_next() -> str:
        raise ValueError("tool exploded")

    with pytest.raises(ValueError):
        await TraceLogExtension().on_tool_call(_context(), ToolCall("call-1", "read_file", {}), call_next)

    assert any("Tool call failed" in message and "tool exploded" in message for message in captured_logs)


async def test_tool_call_summarizes_an_image_result(captured_logs) -> None:
    image = ImageContent(source=ImageBytesSource(data=b"png-bytes", media_type="image/png"))

    async def call_next() -> object:
        return image

    await TraceLogExtension().on_tool_call(_context(), ToolCall("call-1", "view_image", {}), call_next)

    completed = next(message for message in captured_logs if "Tool call completed" in message)
    assert "result=<image result>" in completed
    assert "png-bytes" not in completed

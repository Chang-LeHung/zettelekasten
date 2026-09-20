"""Lossless server-sent event projection for zett-agent events."""

import base64
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from enum import Enum

from zett_agent import (
    AgentEvent,
    AgentEventDispatcher,
    AssistantMessage,
    ImageContent,
    ImageUrlSource,
    ToolCall,
    ToolMessage,
    UserMessage,
)

from ..messages import FrontMessagePart, MessagePartCodec

type SSESend = Callable[[str], Awaitable[None]]

_CODEC = MessagePartCodec()


def encode_sse(name: str, payload: object) -> str:
    """Encode one JSON SSE frame terminated by the required blank line."""
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    return f"event: {name}\ndata: {data}\n\n"


def _json_default(value: object) -> object:
    """Serialize framework dataclasses and enums without exposing exceptions."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ImageContent):
        source = value.source
        url = (
            source.url
            if isinstance(source, ImageUrlSource)
            else f"data:{source.media_type};base64,{base64.b64encode(source.data).decode('ascii')}"
        )
        return {"type": "image", "url": url, "alt_text": value.alt_text}
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)  # type: ignore[arg-type]
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _tool_call(call: ToolCall) -> dict[str, object]:
    return {"id": call.id, "name": call.name, "arguments": dict(call.arguments)}


def user_message_parts(message: UserMessage) -> list[FrontMessagePart]:
    """Project ordered user content blocks, including images, for browser display."""
    return _CODEC.to_front_parts(message.parts)


def _message(message: AssistantMessage | ToolMessage) -> dict[str, object]:
    match message:
        case AssistantMessage():
            return {
                "role": "assistant",
                "content": message.content,
                "reasoning": message.reasoning,
                "tool_calls": [_tool_call(call) for call in message.tool_calls],
                "provider": message.provider,
                "model": message.model,
                "attributes": message.attributes,
            }
        case ToolMessage():
            try:
                output: object = json.loads(message.content) if isinstance(message.content, str) else message.content
            except json.JSONDecodeError:
                output = message.content
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "name": message.name,
                "success": message.success,
                "output": output,
                "attributes": message.attributes,
            }


def event_payload(event: AgentEvent) -> dict[str, object]:
    """Project only fields meaningful for the event while preserving identity."""
    payload: dict[str, object] = {
        "session_id": event.session_id,
        "phase": event.phase.value if event.phase is not None else None,
    }
    if event.delta:
        payload["delta"] = event.delta
    if event.tool_call_delta is not None:
        payload["tool_call_delta"] = asdict(event.tool_call_delta)
    if event.tool_calls:
        payload["tool_calls"] = [_tool_call(call) for call in event.tool_calls]
    if event.server_tool_call is not None:
        payload["server_tool_call"] = {
            "id": event.server_tool_call.id,
            "name": event.server_tool_call.name,
            "input": dict(event.server_tool_call.input) if event.server_tool_call.input is not None else None,
        }
    if event.server_tool_input_delta is not None:
        payload["server_tool_input_delta"] = asdict(event.server_tool_input_delta)
    if event.server_tool_result is not None:
        payload["server_tool_result"] = {
            "call_id": event.server_tool_result.call_id,
            "name": event.server_tool_result.name,
            "output": event.server_tool_result.output,
            "error_code": event.server_tool_result.error_code,
        }
    if event.message is not None:
        payload["message"] = _message(event.message)
    if event.response is not None:
        payload["finish_reason"] = event.response.finish_reason
        payload["usage"] = asdict(event.response.usage)
    if event.internal_message is not None:
        payload["internal_message"] = {
            "content": event.internal_message.content,
            "attributes": event.internal_message.attributes,
        }
    if event.steering_message is not None:
        payload["steering_message"] = {
            "text": event.steering_message.text,
            "parts": [part.model_dump() for part in user_message_parts(event.steering_message)],
            "attributes": event.steering_message.attributes,
        }
    if event.error is not None:
        payload["error"] = {"type": type(event.error).__name__, "message": str(event.error)}
    if event.compaction is not None:
        payload["compaction"] = asdict(event.compaction)
    if event.applied is not None:
        payload["applied"] = event.applied
    if event.name is not None:
        payload["name"] = event.name
    if event.payload is not None:
        payload["payload"] = event.payload
    return payload


class ZettelkastenEventDispatcher(AgentEventDispatcher):
    """Send every zett-agent event as one ordered SSE frame.

    The SSE event name is exactly ``AgentEvent.type.value``. Every payload has
    ``session_id`` and ``phase``; type-specific fields retain their framework
    names: ``delta``, ``tool_call_delta``, ``tool_calls``, ``message``,
    ``server_tool_call``, ``server_tool_input_delta``, ``server_tool_result``,
    ``finish_reason``, ``usage``, ``internal_message``, ``steering_message``,
    ``error``, ``compaction``, ``applied``, ``name``, and ``payload``.

    The injected callable is awaited before the AgentClient advances, preserving
    event order and applying backpressure. Callback errors propagate and cancel
    the active stream through AgentClient's normal lifecycle. This dispatcher
    does not interpret tool names or access application storage.

    SSE protocol::

        event: text_delta
        data: {"session_id":"...","phase":"generating","delta":"Hello"}

        event: server_tool_started
        data: {"session_id":"...","phase":"generating","server_tool_call":{"id":"srvtoolu_1","name":"web_fetch","input":null}}

        event: server_tool_input_delta
        data: {"session_id":"...","phase":"generating","server_tool_input_delta":{"call_id":"srvtoolu_1","delta":"{\"url\":...}"}}

        event: server_tool_completed
        data: {"session_id":"...","phase":"generating","server_tool_result":{"call_id":"srvtoolu_1","name":"web_fetch","output":{...},"error_code":null}}

    ``message.output`` is decoded JSON when a ToolMessage contains valid JSON;
    otherwise it remains a string. Exceptions expose only type and message.
    Provider replay blocks are intentionally omitted from browser transport.
    """

    def __init__(self, send: SSESend) -> None:
        self._send = send

    async def dispatch(self, event: AgentEvent) -> None:
        """Encode and send one framework event without business-specific routing."""
        await self._send(encode_sse(event.type.value, event_payload(event)))

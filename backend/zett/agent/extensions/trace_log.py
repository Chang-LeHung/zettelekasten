"""Log every model request and local tool call around the handler it wraps.

The browser shows a turn as it streams, but a headless run and a request that
never reaches the UI are only visible in the log. This extension wraps both
middlewares so each provider step and each tool call leaves one short line
before it starts and one when it settles, with the ids that tie them to a
conversation and a request.

Text is capped by ``log_preview`` and tool arguments are serialized only to be
previewed, so a large artifact body or an image result stays one short line.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from time import monotonic
from typing import Any

from zett_agent import (
    AgentExtension,
    AgentRunContext,
    ImageContent,
    ModelEvent,
    ModelEventType,
    ModelRequest,
    ToolCall,
)
from zett_agent.tools import ToolResult

from ...infra.log import get_logger, log_preview

logger = get_logger(__name__)

#: One character more than a preview keeps: enough for ``log_preview`` to know
#: the text continues and to add its ellipsis.
_SAMPLE_CHARS = 60 + 1


class TraceLogExtension(AgentExtension):
    """Write one short line before and after each model step and tool call."""

    async def on_model_request(
        self,
        context: AgentRunContext,
        request: ModelRequest,
        call_next: Any,
    ) -> AsyncIterator[ModelEvent]:
        """Log the provider step, stream it untouched, and log how it settled."""
        session_id = context.config.session_id
        request_id = context.config.request_id
        started = monotonic()
        logger.info(
            "Model request; session_id=%s request_id=%s messages=%d tools=%d reasoning=%s last=%s",
            session_id,
            request_id,
            len(request.messages),
            len(request.tools),
            request.reasoning_effort.value,
            _message_preview(request.messages[-1] if request.messages else None),
        )
        chars = 0
        sample = ""
        try:
            async with aclosing(call_next(request)) as events:
                async for event in events:
                    if event.type is ModelEventType.TEXT_DELTA:
                        delta = event.delta or ""
                        chars += len(delta)
                        if len(sample) < _SAMPLE_CHARS:
                            sample += delta[: _SAMPLE_CHARS - len(sample)]
                    yield event
        except asyncio.CancelledError:
            logger.warning(
                "Model request cancelled; session_id=%s request_id=%s duration_ms=%.0f",
                session_id,
                request_id,
                _elapsed_ms(started),
            )
            raise
        except Exception as error:
            logger.warning(
                "Model request failed; session_id=%s request_id=%s duration_ms=%.0f error=%s",
                session_id,
                request_id,
                _elapsed_ms(started),
                log_preview(f"{type(error).__name__}: {error}"),
            )
            raise
        logger.info(
            "Model response; session_id=%s request_id=%s chars=%d duration_ms=%.0f text=%r",
            session_id,
            request_id,
            chars,
            _elapsed_ms(started),
            log_preview(sample),
        )

    async def on_tool_call(
        self,
        context: AgentRunContext,
        call: ToolCall,
        call_next: Any,
    ) -> ToolResult:
        """Log one local tool call, run it, and log what it returned."""
        session_id = context.config.session_id
        request_id = context.config.request_id
        started = monotonic()
        logger.info(
            "Tool call; session_id=%s request_id=%s tool=%s args=%s",
            session_id,
            request_id,
            call.name,
            log_preview(_json_text(call.arguments)),
        )
        try:
            result = await call_next()
        except asyncio.CancelledError:
            logger.warning(
                "Tool call cancelled; session_id=%s request_id=%s tool=%s duration_ms=%.0f",
                session_id,
                request_id,
                call.name,
                _elapsed_ms(started),
            )
            raise
        except Exception as error:
            logger.warning(
                "Tool call failed; session_id=%s request_id=%s tool=%s duration_ms=%.0f error=%s",
                session_id,
                request_id,
                call.name,
                _elapsed_ms(started),
                log_preview(f"{type(error).__name__}: {error}"),
            )
            raise
        logger.info(
            "Tool call completed; session_id=%s request_id=%s tool=%s duration_ms=%.0f result=%s",
            session_id,
            request_id,
            call.name,
            _elapsed_ms(started),
            _result_preview(result),
        )
        return result


def _elapsed_ms(started: float) -> float:
    return (monotonic() - started) * 1_000


def _json_text(value: Any) -> str:
    """Serialize one tool payload for previewing without raising on odd values."""
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def _message_preview(message: Any) -> str:
    """Name the newest request message and preview its text, never its pixels."""
    if message is None:
        return "none"
    role = getattr(message, "role", None)
    name = getattr(role, "value", role) or "message"
    text = _message_text(message)
    return f"{name}:{log_preview(text)!r}" if text else str(name)


def _message_text(message: Any) -> str:
    """Project one provider-neutral message onto the text a reader wants to see."""
    text = getattr(message, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        if any(isinstance(part, ImageContent) for part in content):
            return "<image>"
        return _json_text(content)
    return ""


def _result_preview(result: ToolResult) -> str:
    """Render one tool result as a short preview, never as encoded pixels."""
    if isinstance(result, ImageContent) or (
        isinstance(result, (list, tuple)) and any(isinstance(item, ImageContent) for item in result)
    ):
        return "<image result>"
    if isinstance(result, (bytes, bytearray)):
        return f"<{len(result)} bytes>"
    return log_preview(_json_text(result) if not isinstance(result, str) else result)


__all__ = ["TraceLogExtension"]

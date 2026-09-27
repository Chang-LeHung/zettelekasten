"""Estimate the semantic composition of the next model request."""

import json
from collections.abc import Awaitable, Callable, Sequence

from zett_agent.agent import (
    AgentRunContext,
)
from zett_agent.events import (
    AgentEvent,
    AgentEventType,
)
from zett_agent.extensions.base import (
    AgentExtension,
)
from zett_agent.messages import (
    AgentMessage,
    AssistantMessage,
    ImageContent,
    SystemMessage,
    TextContent,
    ToolMessage,
    UserMessage,
)
from zett_agent.model import (
    ModelRequest,
    ModelResponse,
)

from ..._compat import TypeAliasType

CONTEXT_COMPOSITION_EVENT = "context_composition"
#: The o200k BPE table costs about a tenth of a second to load, and a process
#: pays it only when a turn records a composition, so it is built on first use
#: instead of at import time.
_ENCODING: object | None = None
_CATEGORIES = ("system_prompt", "tool_prompt", "tool_output", "user", "assistant")
_IMAGE_TOKEN_ESTIMATE = 1_100
ContextCompositionRecorder = TypeAliasType(
    "ContextCompositionRecorder", Callable[[str, dict[str, float]], Awaitable[None]]
)


def _content_token_count(content: object) -> int:
    """Count text and bounded image estimates without serializing image bytes."""
    if isinstance(content, str):
        return _token_count(content)
    if not isinstance(content, Sequence):
        return _token_count(content)
    total = 0
    for part in content:
        if isinstance(part, TextContent):
            total += _token_count(part.text)
        elif isinstance(part, ImageContent):
            total += _IMAGE_TOKEN_ESTIMATE
        else:
            total += _token_count(repr(part))
    return total


def _token_count(value: object) -> int:
    """Count one normalized value with the same tokenizer for every category."""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=repr)
    return len(_encoding().encode_ordinary(text))


def _encoding() -> object:
    """Return the shared o200k encoding, loading ``tiktoken`` on first use."""
    global _ENCODING
    if _ENCODING is None:
        import tiktoken

        _ENCODING = tiktoken.get_encoding("o200k_base")
    return _ENCODING


def _tool_payload(request: ModelRequest) -> dict[str, object]:
    """Return only provider-visible local and hosted tool definitions."""
    return {
        "tools": [
            {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)}
            for tool in request.tools
        ],
        "server_tools": [
            {"type": tool.type, "configuration": dict(tool.configuration)} for tool in request.server_tools
        ],
    }


def context_composition(request: ModelRequest) -> dict[str, float]:
    """Return request-category ratios; absolute estimates stay on the server.

    ``tiktoken`` is intentionally used for every category so the proportions
    remain internally comparable across providers. They are estimates rather
    than billing counters: providers tokenize wrappers, images, and hosted-tool
    schemas differently. The browser therefore receives ratios only.
    """
    counts = dict.fromkeys(_CATEGORIES, 0)
    for message in request.messages:
        match message:
            case SystemMessage(content=content):
                category = (
                    "tool_prompt"
                    if content.lstrip().startswith(("# Tool snippets", "# Tool guidelines"))
                    else "system_prompt"
                )
                counts[category] += _token_count(content)
            case ToolMessage(content=content):
                counts["tool_output"] += _content_token_count(content)
            case UserMessage(content=content):
                counts["user"] += _content_token_count(content)
            case AssistantMessage():
                counts["assistant"] += _token_count(
                    {"content": message.content, "reasoning": message.reasoning, "tool_calls": message.tool_calls}
                )
            case AgentMessage(content=content):
                # Providers map internal AgentMessage input to the user role.
                # Report it under the same category the model ultimately sees.
                counts["user"] += _token_count(content)

    tool_payload = _tool_payload(request)
    if tool_payload["tools"] or tool_payload["server_tools"]:
        counts["tool_prompt"] += _token_count(tool_payload)

    total = sum(counts.values())
    if total == 0:
        return {category: 0.0 for category in _CATEGORIES}
    return {category: count / total for category, count in counts.items()}


class ContextCompositionExtension(AgentExtension):
    """Publish and persist context ratios for every primary model request.

    ``before_model`` measures the outgoing request, which is exactly the context
    the provider receives, and ``after_model`` refreshes that view once the
    assistant message is appended. Tool results only exist after their own model
    step, so tool output reaches the report on the following before-model view.
    """

    def __init__(self, recorder: ContextCompositionRecorder | None = None) -> None:
        self._recorder = recorder

    async def before_model(self, context: AgentRunContext, request: ModelRequest) -> None:
        """Report the ratios of the request that is about to reach the provider."""
        await self._publish(context, request)

    async def after_model(self, context: AgentRunContext, response: ModelResponse) -> None:
        """Report the ratios again after the complete assistant message is appended."""
        del response
        await self._publish(context, self._live_request(context))

    @staticmethod
    def _live_request(context: AgentRunContext) -> ModelRequest:
        """Rebuild the provider-visible request from the mutated run context."""
        return ModelRequest(
            messages=tuple(context.state.messages),
            tools=tuple(tool.definition for tool in context.tools.values()),
            server_tools=tuple(context.server_tools.values()),
        )

    async def _publish(self, context: AgentRunContext, request: ModelRequest) -> None:
        """Record one browser-safe ratio payload and stream it to the caller."""
        ratios = context_composition(request)
        if self._recorder is not None:
            await self._recorder(context.config.session_id, ratios)
        await context.emit(
            AgentEvent(
                AgentEventType.CUSTOM,
                context.config.session_id,
                name=CONTEXT_COMPOSITION_EVENT,
                payload=ratios,
            )
        )

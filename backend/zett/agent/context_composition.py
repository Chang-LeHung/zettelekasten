"""Estimate the semantic composition of the next model request."""

import json
from collections.abc import AsyncIterator

import tiktoken
from zett_agent import (
    AgentEvent,
    AgentEventType,
    AgentExtension,
    AgentMessage,
    AgentRunContext,
    AssistantMessage,
    ModelRequest,
    ModelResponse,
    SystemMessage,
    ToolMessage,
    UserMessage,
)

CONTEXT_COMPOSITION_EVENT = "context_composition"
_ENCODING = tiktoken.get_encoding("o200k_base")
_CATEGORIES = ("system_prompt", "tool_prompt", "tool_output", "user", "assistant")


def _token_count(value: object) -> int:
    """Count one normalized value with the same tokenizer for every category."""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=repr)
    return len(_ENCODING.encode_ordinary(text))


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
                counts["tool_output"] += _token_count(content)
            case UserMessage():
                counts["user"] += _token_count(repr(message.content))
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
    """Publish context ratios before a model call and after its response."""

    @staticmethod
    def _event(context: AgentRunContext, request: ModelRequest) -> AgentEvent:
        """Create one browser-safe ratio event for the supplied context view."""
        return AgentEvent(
            AgentEventType.CUSTOM,
            context.config.session_id,
            name=CONTEXT_COMPOSITION_EVENT,
            payload=context_composition(request),
        )

    async def before_model_events(
        self,
        context: AgentRunContext,
        request: ModelRequest,
    ) -> AsyncIterator[AgentEvent]:
        """Expose proportions without leaking prompts, tool output, or token estimates."""
        yield self._event(context, request)

    async def after_model_events(
        self,
        context: AgentRunContext,
        response: ModelResponse,
    ) -> AsyncIterator[AgentEvent]:
        """Publish the context again after the complete Assistant message is appended.

        The response argument identifies this lifecycle boundary; its message is
        already present in ``context.state.messages``. Tool results do not exist
        yet at this point. When tools run, the next before-model event naturally
        includes their output in the following request's proportions.
        """
        del response
        request = ModelRequest(
            messages=tuple(context.state.messages),
            tools=tuple(tool.definition for tool in context.tools.values()),
            server_tools=tuple(context.server_tools.values()),
        )
        yield self._event(context, request)

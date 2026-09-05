"""Provider-neutral structured output validated at the application boundary."""

from collections.abc import Sequence

from kcs_agent import (
    AgentModel,
    AnyMessage,
    ModelEventType,
    ModelRequest,
    ReasoningEffort,
    ToolDefinition,
)
from pydantic import BaseModel


async def structured_output[OutputT: BaseModel](
    model: AgentModel,
    schema: type[OutputT],
    messages: Sequence[AnyMessage],
) -> OutputT:
    """Require one schema-bound response tool and validate its arguments without parsing prose."""
    name = "submit_result"
    request = ModelRequest(
        messages=messages,
        tools=(ToolDefinition(name, "Submit the requested structured result.", schema.model_json_schema()),),
        tool_choice=name,
        reasoning_effort=ReasoningEffort.OFF,
    )
    result: OutputT | None = None
    async for event in model.stream(request):
        if event.type == ModelEventType.RESPONSE:
            if result is not None or event.response is None:
                raise ValueError("Invalid structured response stream")
            calls = event.response.message.tool_calls
            if len(calls) != 1 or calls[0].name != name:
                raise ValueError("Model must return exactly one submit_result tool call")
            result = schema.model_validate(dict(calls[0].arguments))
    if result is None:
        raise ValueError("Model did not return a structured response")
    return result

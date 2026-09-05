"""Adapt schema-validated application operations to the standalone agent runtime."""

import asyncio
from collections.abc import Callable

from kcs_agent import AgentTool
from pydantic import BaseModel, ConfigDict


class EmptyToolInput(BaseModel):
    """Reject arguments for operations that accept no input."""

    model_config = ConfigDict(extra="forbid")


def typed_tool(
    name: str,
    operation: Callable[..., object],
    schema: type[BaseModel] | None,
    guideline: str,
) -> AgentTool:
    """Validate nested models before dispatch and keep blocking operations off the event loop."""
    input_schema = schema or EmptyToolInput

    async def invoke(**arguments: object) -> object:
        parsed = input_schema.model_validate(arguments)
        values = {field: getattr(parsed, field) for field in type(parsed).model_fields}
        return await asyncio.to_thread(operation, **values)

    description = (operation.__doc__ or name).strip().split("\n\n", 1)[0]
    return AgentTool(
        name=name,
        description=description,
        parameters=input_schema.model_json_schema(),
        handler=invoke,
        guidelines=guideline,
    )

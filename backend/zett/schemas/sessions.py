"""Write models for persisted Agent conversations."""

from pydantic import BaseModel, Field


class AgentSessionCreate(BaseModel):
    """Complete mutable fields for a persisted Agent conversation."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Optional user-facing conversation title",
    )

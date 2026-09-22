"""Typed payloads for built-in scheduled task actions."""

from pydantic import BaseModel, ConfigDict, Field
from zett_agent import ReasoningEffort

AGENT_PROMPT_ACTION_KIND = "agent_prompt"


class AgentPromptAction(BaseModel):
    """One scheduled turn that always runs in a new isolated Agent session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1, max_length=36)
    message: str = Field(min_length=1, max_length=100_000)
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM

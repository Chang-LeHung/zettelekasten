"""Reusable application facade around one multi-session zett-agent runtime."""

from collections.abc import Sequence
from typing import Self

from zett_agent import (
    Agent,
    AgentClient,
    AgentEventDispatcher,
    AgentExtension,
    AgentModel,
    AgentRunConfig,
    AgentTool,
    ExternalEvent,
    ReasoningEffort,
    create_agent,
    new_uuid7,
)


class ZettelkastenAgent:
    """Own one conversation Agent while requests provide models and dispatchers.

    A lightweight AgentClient is created per HTTP request so each response
    owns its own SSE dispatcher. Provider adapters remain request-scoped and
    override the optional default model without mutating this session Agent.
    """

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    @classmethod
    async def create(
        cls,
        model: AgentModel | None = None,
        *,
        config: AgentRunConfig | None = None,
        system_prompt: str = "",
        tools: Sequence[AgentTool] = (),
        extensions: Sequence[AgentExtension] = (),
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
        max_iterations: int = 36,
    ) -> Self:
        """Create one initialized conversation runtime."""
        client = await create_agent(
            model,
            config=config or AgentRunConfig(session_id=new_uuid7()),
            system_prompt=system_prompt,
            tools=tools,
            extensions=extensions,
            reasoning_effort=reasoning_effort,
            max_iterations=max_iterations,
        )
        return cls(client.agent)

    def client(self, dispatcher: AgentEventDispatcher) -> AgentClient:
        """Bind a request-owned dispatcher to this conversation runtime."""
        return AgentClient(self.agent, event_dispatcher=dispatcher)

    def emit_external_event(self, event: ExternalEvent, *, config: AgentRunConfig) -> list[str]:
        """Route external input to extensions handling the identified request."""
        return self.agent.emit_external_event(event, config=config)

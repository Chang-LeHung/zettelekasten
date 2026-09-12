"""Reusable application facade around one multi-session zett-agent runtime."""

from collections.abc import Sequence
from typing import Self

from zett_agent import (
    Agent,
    AgentClient,
    AgentConfig,
    AgentEventDispatcher,
    AgentExtension,
    AgentModel,
    AgentTool,
    ExternalEvent,
    ReasoningEffort,
    create_agent,
    new_uuid7,
)


class ZettelkastenAgent:
    """Own one reusable Agent while requests provide models and dispatchers.

    The underlying Agent isolates mutable state by session ID and rejects two
    overlapping requests for the same session. A lightweight AgentClient is
    created per HTTP request so each response owns its own SSE dispatcher.
    Provider adapters are request-scoped and override the optional default
    model without mutating this shared instance.
    """

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    @classmethod
    async def create(
        cls,
        model: AgentModel | None = None,
        *,
        config: AgentConfig | None = None,
        system_prompt: str = "",
        tools: Sequence[AgentTool] = (),
        extensions: Sequence[AgentExtension] = (),
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
        max_iterations: int = 36,
    ) -> Self:
        """Create one initialized runtime that can serve many sessions."""
        client = await create_agent(
            model,
            config=config or AgentConfig(session_id=new_uuid7()),
            system_prompt=system_prompt,
            tools=tools,
            extensions=extensions,
            reasoning_effort=reasoning_effort,
            max_iterations=max_iterations,
        )
        return cls(client.agent)

    def client(self, dispatcher: AgentEventDispatcher) -> AgentClient:
        """Bind a request-owned dispatcher to the shared Agent runtime."""
        return AgentClient(self.agent, event_dispatcher=dispatcher)

    def emit_external_event(self, event: ExternalEvent, *, config: AgentConfig) -> list[str]:
        """Route external input to extensions handling the identified request."""
        return self.agent.emit_external_event(event, config=config)

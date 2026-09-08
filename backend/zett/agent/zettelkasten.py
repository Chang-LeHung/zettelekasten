"""Small application facade around zett-agent's standard AgentClient."""

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import aclosing
from typing import Self

from zett_agent import (
    AgentClient,
    AgentConfig,
    AgentEvent,
    AgentExtension,
    AgentModel,
    AgentTool,
    AssistantMessage,
    JsonValue,
    ReasoningEffort,
    UserMessage,
    create_agent,
    new_uuid7,
)

from .dispatcher import SSESend, ZettelkastenEventDispatcher


class ZettelkastenAgent:
    """Create and use one zett-agent client with an injected SSE sender.

    Use :meth:`create` because zett-agent initialization is asynchronous. The
    class owns no provider, database, HTTP response, tool policy, or business
    state. Callers compose those concerns through the model, extensions, tools,
    and send callable.

    Example::

        async def send(frame: str) -> None:
            await response.write(frame)

        agent = await ZettelkastenAgent.create(model, send=send)
        answer = await agent.run("Turn this thought into a card")
    """

    def __init__(self, client: AgentClient, dispatcher: ZettelkastenEventDispatcher) -> None:
        self.client = client
        self.dispatcher = dispatcher

    @classmethod
    async def create(
        cls,
        model: AgentModel,
        *,
        send: SSESend,
        config: AgentConfig | None = None,
        system_prompt: str = "",
        tools: Sequence[AgentTool] = (),
        extensions: Sequence[AgentExtension] = (),
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
        max_iterations: int = 12,
    ) -> Self:
        """Build the underlying AgentClient with a request-ordered SSE dispatcher."""
        dispatcher = ZettelkastenEventDispatcher(send)
        client = await create_agent(
            model,
            config=config or AgentConfig(session_id=new_uuid7()),
            event_dispatcher=dispatcher,
            system_prompt=system_prompt,
            tools=tools,
            extensions=extensions,
            reasoning_effort=reasoning_effort,
            max_iterations=max_iterations,
        )
        return cls(client, dispatcher)

    async def stream(
        self,
        message: UserMessage | str,
        *,
        config: AgentConfig | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
        tags: Mapping[str, JsonValue] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Yield original events after their corresponding SSE frame is sent."""
        async with aclosing(
            self.client.stream(
                message,
                config=config,
                reasoning_effort=reasoning_effort,
                metadata=metadata,
                tags=tags,
            )
        ) as events:
            async for event in events:
                yield event

    async def run(
        self,
        message: UserMessage | str,
        *,
        config: AgentConfig | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
        tags: Mapping[str, JsonValue] | None = None,
    ) -> AssistantMessage:
        """Return the final answer while sending every intermediate SSE frame."""
        return await self.client.run(
            message,
            config=config,
            reasoning_effort=reasoning_effort,
            metadata=metadata,
            tags=tags,
        )

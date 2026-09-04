from typing import cast

import pytest
from langchain_core.language_models import BaseChatModel

from kcs.agent.session_title_agent import SessionTitleAgent, SessionTitleOutput
from kcs.infra.agent_session_dao import agent_session_storage
from kcs.models import AIProviderRuntime
from kcs.schemas import AgentMessageRole, AgentSessionCreate


class FakeTitleModel:
    def __init__(self) -> None:
        self.calls = 0

    def with_structured_output(self, schema: type[SessionTitleOutput]) -> FakeTitleModel:
        assert schema is SessionTitleOutput
        return self

    async def ainvoke(self, _messages: object) -> SessionTitleOutput:
        self.calls += 1
        return SessionTitleOutput(title='"将 Agent 流程抽象为 DSL"')


def test_clean_title_removes_model_formatting() -> None:
    assert SessionTitleOutput(title='## "Knowledge cards"\nExtra text').title == "Knowledge cards"


@pytest.mark.asyncio
async def test_title_agent_silently_updates_session() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    agent_session_storage.append_message(
        session.id,
        "turn-1",
        AgentMessageRole.USER,
        "Please turn an agent workflow into an executable DSL.",
    )
    agent_session_storage.append_message(
        session.id,
        "turn-1",
        AgentMessageRole.ASSISTANT,
        "The DSL separates language semantics from execution.",
    )
    model = FakeTitleModel()
    agent = SessionTitleAgent(
        lambda _provider_id, _reasoning_effort: (
            AIProviderRuntime(provider="fake", model="title-model"),
            cast(BaseChatModel, model),
        )
    )

    await agent.summarize(session.id, 1)
    await agent.summarize(session.id, 1)

    updated = agent_session_storage.get(session.id)
    assert updated is not None
    assert updated.title == "将 Agent 流程抽象为 DSL"
    assert updated.metadata["title_generated_by"] == "KCS Session Title Agent"
    assert updated.metadata["title_message_count"] == 2
    assert updated.metadata["title_finalized"] is True
    assert model.calls == 1

    agent_session_storage.append_message(
        session.id,
        "turn-2",
        AgentMessageRole.USER,
        "Now add a parser example.",
    )
    await agent.summarize(session.id, 1)

    refreshed = agent_session_storage.get(session.id)
    assert refreshed is not None
    assert refreshed.metadata["title_message_count"] == 2
    assert model.calls == 1


@pytest.mark.asyncio
async def test_title_agent_does_not_replace_an_explicit_title() -> None:
    session = agent_session_storage.create(AgentSessionCreate(title="My title", metadata={"title_source": "user"}))
    agent_session_storage.append_message(session.id, "turn-1", AgentMessageRole.USER, "Hello")
    agent_session_storage.append_message(session.id, "turn-1", AgentMessageRole.ASSISTANT, "Hello back")
    model = FakeTitleModel()
    agent = SessionTitleAgent(
        lambda _provider_id, _reasoning_effort: (
            AIProviderRuntime(provider="fake", model="title-model"),
            cast(BaseChatModel, model),
        )
    )

    await agent.summarize(session.id, 1)

    unchanged = agent_session_storage.get(session.id)
    assert unchanged is not None
    assert unchanged.title == "My title"
    assert model.calls == 0


@pytest.mark.asyncio
async def test_title_agent_waits_for_a_non_cancelled_response() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    agent_session_storage.append_message(session.id, "turn-1", AgentMessageRole.USER, "Explain cancellation.")
    agent_session_storage.append_message(
        session.id,
        "turn-1",
        AgentMessageRole.ASSISTANT,
        "A partial answer",
        metadata={"cancelled": True},
    )
    model = FakeTitleModel()
    agent = SessionTitleAgent(
        lambda _provider_id, _reasoning_effort: (
            AIProviderRuntime(provider="fake", model="title-model"),
            cast(BaseChatModel, model),
        )
    )

    await agent.summarize(session.id, 1)

    unchanged = agent_session_storage.get(session.id)
    assert unchanged is not None
    assert unchanged.title is None
    assert unchanged.metadata.get("title_generation_attempted") is None
    assert model.calls == 0

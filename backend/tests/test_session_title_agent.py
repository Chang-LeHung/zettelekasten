from typing import cast

import pytest
from kcs_agent import AgentModel, AssistantMessage, ModelEvent, ModelResponse, ToolCall, UserMessage

from kcs.agent.session_title_agent import SessionTitleAgent, SessionTitleOutput
from kcs.infra.agent_runtime import get_agent_runtime_storage
from kcs.infra.agent_session_dao import agent_session_storage
from kcs.models import AIProviderRuntime
from kcs.schemas import AgentRunStatus, AgentSessionCreate, ReasoningEffort


async def append_messages(session_id: str, request_id: str, *messages) -> None:
    """Append typed runtime messages through kcs-agent's authoritative store."""
    storage = get_agent_runtime_storage()
    for message in messages:
        await storage.append(session_id, request_id, message)


def complete_run(session_id: str, request_id: str) -> None:
    """Create a successful observable KCS run for title eligibility."""
    run = agent_session_storage.start_run(session_id, request_id, None, "fake", "model", ReasoningEffort.OFF)
    agent_session_storage.finish_run(run.id, AgentRunStatus.SUCCEEDED, {})


class FakeTitleModel:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, request):
        assert request.tools[0].parameters == SessionTitleOutput.model_json_schema()
        assert request.tool_choice == "submit_result"
        self.calls += 1
        yield ModelEvent.completed(
            ModelResponse(
                AssistantMessage(tool_calls=(ToolCall("title-1", "submit_result", {"title": "Agent workflow DSL"}),))
            )
        )


def test_clean_title_removes_model_formatting() -> None:
    assert SessionTitleOutput(title='## "Knowledge cards"\nExtra text').title == "Knowledge cards"


@pytest.mark.asyncio
async def test_title_agent_silently_updates_session() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    await append_messages(
        session.id,
        "turn-1",
        UserMessage(content="Please turn an agent workflow into an executable DSL."),
        AssistantMessage(content="The DSL separates language semantics from execution."),
    )
    complete_run(session.id, "turn-1")
    model = FakeTitleModel()
    agent = SessionTitleAgent(
        lambda _provider_id: (
            AIProviderRuntime(provider="fake", model="title-model"),
            cast(AgentModel, model),
        )
    )

    await agent.summarize(session.id, 1)
    await agent.summarize(session.id, 1)

    updated = agent_session_storage.get(session.id)
    assert updated is not None
    assert updated.title == "Agent workflow DSL"
    assert updated.metadata["title_generated_by"] == "KCS Session Title Agent"
    assert updated.metadata["title_message_count"] == 2
    assert updated.metadata["title_finalized"] is True
    assert model.calls == 1

    await append_messages(session.id, "turn-2", UserMessage(content="Now add a parser example."))
    await agent.summarize(session.id, 1)

    refreshed = agent_session_storage.get(session.id)
    assert refreshed is not None
    assert refreshed.metadata["title_message_count"] == 2
    assert model.calls == 1


@pytest.mark.asyncio
async def test_title_agent_does_not_replace_an_explicit_title() -> None:
    session = agent_session_storage.create(AgentSessionCreate(title="My title", metadata={"title_source": "user"}))
    await append_messages(session.id, "turn-1", UserMessage(content="Hello"), AssistantMessage(content="Hello back"))
    complete_run(session.id, "turn-1")
    model = FakeTitleModel()
    agent = SessionTitleAgent(
        lambda _provider_id: (
            AIProviderRuntime(provider="fake", model="title-model"),
            cast(AgentModel, model),
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
    await append_messages(
        session.id,
        "turn-1",
        UserMessage(content="Explain cancellation."),
        AssistantMessage(content="A partial answer"),
    )
    run = agent_session_storage.start_run(session.id, "turn-1", None, "fake", "model", ReasoningEffort.OFF)
    agent_session_storage.finish_run(run.id, AgentRunStatus.CANCELLED, {})
    model = FakeTitleModel()
    agent = SessionTitleAgent(
        lambda _provider_id: (
            AIProviderRuntime(provider="fake", model="title-model"),
            cast(AgentModel, model),
        )
    )

    await agent.summarize(session.id, 1)

    unchanged = agent_session_storage.get(session.id)
    assert unchanged is not None
    assert unchanged.title is None
    assert unchanged.metadata.get("title_generation_attempted") is None
    assert model.calls == 0

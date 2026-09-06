import asyncio
import json
from collections.abc import AsyncIterator
from typing import cast

import pytest
from zett_agent import (
    AssistantMessage,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ToolCall,
)

from zett import config
from zett.agent import card_agent
from zett.infra.agent_session_dao import agent_session_storage
from zett.models import AIProviderRuntime
from zett.schemas import AgentRunStatus, AgentSessionCreate, AnalysisMessage, AnalyzeRequest, ReasoningEffort

CARD_DRAFT = {
    "artifact_type": "card",
    "card_type": "idea",
    "title": "Streaming knowledge cards",
    "summary": "Expose every observable agent stage in real time.",
    "content": "Reasoning, tools, output, and metrics use separate SSE events.",
    "suggested_tags": [],
    "keywords": ["streaming", "SSE"],
}

ARTICLE_DRAFT = {
    "artifact_type": "article",
    "title": "Streaming agent architecture",
    "subtitle": "From events to durable outputs",
    "summary": "A longer explanation of observable agent execution.",
    "content": "# Architecture\n\nPersist every meaningful event.",
    "suggested_tags": [],
    "keywords": ["agents", "architecture"],
}


class StreamingTestModel:
    """Deterministic provider-neutral model double for runtime integration tests."""

    def __init__(self) -> None:
        self.calls = 0
        self.tool_names: list[str] = []
        self.received_context = ""

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.calls += 1
        self.tool_names = [item.name for item in request.tools]
        self.received_context = "\n".join(str(message.content) for message in request.messages)
        async for event in self.generate():
            yield event

    async def generate(self) -> AsyncIterator[ModelEvent]:
        yield ModelEvent.completed(ModelResponse(AssistantMessage(content="unused")))


def completed(
    text: str = "",
    calls: tuple[ToolCall, ...] = (),
    usage: ModelUsage = ModelUsage(),
    reasoning: str | None = None,
) -> ModelEvent:
    return ModelEvent.completed(
        ModelResponse(
            AssistantMessage(content=text, reasoning=reasoning, tool_calls=calls),
            finish_reason="tool_calls" if calls else "stop",
            usage=usage,
        )
    )


class SuccessfulStreamingModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        if self.calls == 1:
            yield ModelEvent.reasoning("I should create a structured card.")
            yield completed(
                calls=(ToolCall("tool-1", "create_card", {"content": CARD_DRAFT}),),
                usage=ModelUsage(input_tokens=12, output_tokens=8, reasoning_tokens=3),
                reasoning="I should create a structured card.",
            )
            return
        yield ModelEvent.text("Created ")
        yield ModelEvent.text("the card.")
        yield completed("Created the card.", usage=ModelUsage(input_tokens=20, output_tokens=4))


class FailingStreamingModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        raise RuntimeError("provider stream failed")
        yield


class ConversationOnlyStreamingModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        yield ModelEvent.text("Let's explore ")
        yield ModelEvent.text("that idea first.")
        yield completed("Let's explore that idea first.", usage=ModelUsage(input_tokens=10, output_tokens=5))


class MultipleArtifactStreamingModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        if self.calls == 1:
            yield completed(
                calls=(
                    ToolCall("card-tool", "create_card", {"content": CARD_DRAFT}),
                    ToolCall("article-tool", "create_article", {"content": ARTICLE_DRAFT}),
                )
            )
            return
        yield ModelEvent.text("Created both artifacts.")
        yield completed("Created both artifacts.")


class FilesystemStreamingModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        if self.calls == 1:
            yield completed(
                calls=(
                    ToolCall(
                        "file-tool",
                        "write_file",
                        {
                            "file_path": "/notes/context.md",
                            "content": "Session-only context.",
                        },
                    ),
                )
            )
            return
        yield ModelEvent.text("Stored a private working note.")
        yield completed("Stored a private working note.")


class FilesystemTraversalModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        if self.calls == 1:
            yield completed(calls=(ToolCall("traversal-tool", "read_file", {"file_path": "/../outside.txt"}),))
            return
        yield ModelEvent.text("The file is outside my workspace.")
        yield completed("The file is outside my workspace.")


class AssetContextStreamingModel(StreamingTestModel):
    async def generate(self) -> AsyncIterator[ModelEvent]:
        yield ModelEvent.text("I used the supplied context.")
        yield completed("I used the supplied context.")


def parse_event(value: str) -> tuple[str, object]:
    lines = value.strip().splitlines()
    name = lines[0].removeprefix("event: ")
    payload = json.loads("\n".join(line.removeprefix("data: ") for line in lines[1:] if line.startswith("data: ")))
    return name, payload


def request() -> AnalyzeRequest:
    return AnalyzeRequest(
        raw_content="Create a card about streaming.",
        provider_id=1,
        messages=[AnalysisMessage(role="user", content="Create a card about streaming.")],
    )


@pytest.mark.asyncio
async def test_stream_publishes_and_persists_complete_agent_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    model = SuccessfulStreamingModel()
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (AIProviderRuntime(provider="fake", model="fake-stream"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    names = [name for name, _ in events]
    tool_events = [cast(dict[str, object], payload) for name, payload in events if name == "tool"]
    message_events = [cast(dict[str, object], payload) for name, payload in events if name == "message"]
    usage_events = [cast(dict[str, object], payload) for name, payload in events if name == "usage"]
    assert {"status", "tool", "usage", "message", "artifacts", "metrics", "result"} <= set(names)
    assert "reasoning" in names
    assert [payload["state"] for payload in tool_events] == ["started", "succeeded"]
    completed_tool_output = cast(dict[str, object], tool_events[-1]["output"])
    completed_tool_content = cast(dict[str, object], completed_tool_output["content"])
    assert completed_tool_content["title"] == "Streaming knowledge cards"
    assert message_events[-1]["content"] == "Created the card."
    assert usage_events[-1]["cache_hit_rate"] == 0
    assert cast(float, usage_events[-1]["output_tokens_per_second"]) > 0
    assert {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute_shell"} <= set(model.tool_names)

    session = card_agent.agent_session_storage.get(session_id)
    assert session is not None
    # The raw log retains the model's tool-call message as well as user, tool,
    # and final assistant messages.
    assert session.message_count == 4
    assert len(session.artifacts) == 1
    assert session.artifacts[0].content.title == "Streaming knowledge cards"
    assert len(session.runs) == 1
    assert session.runs[0].status == AgentRunStatus.SUCCEEDED
    assert session.runs[0].total_tokens == 44
    assert session.runs[0].reasoning_effort == ReasoningEffort.OFF
    assert session.runs[0].reasoning_tokens == 3
    assert session.runs[0].tool_calls[0].tool_name == "create_card"
    assert session.messages[-1].reasoning_content == "I should create a structured card."
    assert session.messages[-1].metadata == {
        "run_id": session.runs[0].id,
        "reasoning_content": "I should create a structured card.",
        "timeline": [
            {"type": "reasoning", "content": "I should create a structured card."},
            {"type": "tool", "tool_call_id": "tool-1"},
            {"type": "message", "content": "Created the card."},
        ],
    }


@pytest.mark.asyncio
async def test_stream_persists_failure_metrics_and_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (
            AIProviderRuntime(provider="fake", model="failing-stream"),
            FailingStreamingModel(),
        ),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    assert events[-1] == ("error", {"message": "provider stream failed"})
    assert any(name == "metrics" for name, _ in events)
    session = card_agent.agent_session_storage.get(session_id)
    assert session is not None
    assert session.status == "failed"
    assert session.runs[0].status == AgentRunStatus.FAILED
    assert session.runs[0].error_type == "RuntimeError"
    assert session.runs[0].error_message == "provider stream failed"


@pytest.mark.asyncio
async def test_stream_allows_conversation_without_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (
            AIProviderRuntime(provider="fake", model="conversation-only"),
            ConversationOnlyStreamingModel(),
        ),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    assert ("message", {"content": "Let's explore that idea first."}) in events
    assert events[-1] == ("result", None)
    assert not any(name == "error" for name, _ in events)
    session = agent_session_storage.get(session_id)
    assert session is not None
    assert session.message_count == 2
    assert session.artifacts == []
    assert session.runs[0].status == AgentRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_stream_cancellation_persists_partial_answer_and_cancelled_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (
            AIProviderRuntime(provider="fake", model="interruptible"),
            ConversationOnlyStreamingModel(),
        ),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    stream = card_agent.zett_agent.stream(session_id, request())
    observed: list[tuple[str, object]] = []
    while not any(name == "message" for name, _ in observed):
        observed.append(parse_event(await anext(stream)))

    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())

    session = agent_session_storage.get(session_id)
    assert session is not None
    assert session.runs[0].status == AgentRunStatus.CANCELLED
    assert session.messages[-1].content == "Let's explore"
    assert session.messages[-1].metadata["cancelled"] is True


@pytest.mark.asyncio
async def test_stream_creates_multiple_artifact_types_in_one_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    model = MultipleArtifactStreamingModel()
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (AIProviderRuntime(provider="fake", model="multi-output"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    artifact_events = [cast(list[dict[str, object]], payload) for name, payload in events if name == "artifacts"]
    assert len(artifact_events[-1]) == 2
    assert {item["artifact_type"] for item in artifact_events[-1]} == {"card", "article"}
    session = agent_session_storage.get(session_id)
    assert session is not None
    assert {artifact.artifact_type.value for artifact in session.artifacts} == {"card", "article"}


@pytest.mark.asyncio
async def test_stream_uses_kcs_filesystem_inside_session_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FilesystemStreamingModel()
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (AIProviderRuntime(provider="fake", model="filesystem"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    tool_events = [cast(dict[str, object], payload) for name, payload in events if name == "tool"]
    assert [event["state"] for event in tool_events] == ["started", "succeeded"]
    assert tool_events[-1]["name"] == "write_file"
    workspace_file = config.settings.asset_directory / session_id / "notes" / "context.md"
    assert workspace_file.read_text(encoding="utf-8") == "Session-only context."


@pytest.mark.asyncio
async def test_kcs_filesystem_rejects_parent_directory_traversal(monkeypatch: pytest.MonkeyPatch) -> None:
    model = FilesystemTraversalModel()
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (AIProviderRuntime(provider="fake", model="filesystem"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    outside_file = config.settings.asset_directory / "outside.txt"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("private", encoding="utf-8")

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    tool_events = [cast(dict[str, object], payload) for name, payload in events if name == "tool"]
    assert tool_events[-1]["name"] == "read_file"
    assert "private" not in json.dumps(tool_events[-1], ensure_ascii=False)


@pytest.mark.asyncio
async def test_zett_agent_receives_asset_content_and_prompt_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    from zett.application.services import SessionAssetApplicationService
    from zett.schemas import SessionTextAssetIn

    model = AssetContextStreamingModel()
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _provider_id: (AIProviderRuntime(provider="fake", model="asset-context"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: ["Engineering/Agents"]))
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    SessionAssetApplicationService.create_text(
        session_id,
        SessionTextAssetIn(name="Research note", content="Asset body supplied directly to Zett Agent."),
    )

    events = [parse_event(value) async for value in card_agent.zett_agent.stream(session_id, request())]

    assert any(name == "result" for name, _ in events)
    assert "Asset body supplied directly to Zett Agent." in model.received_context
    assert "<session_asset_content>" in model.received_context
    assert "untrusted reference data" in model.received_context
    assert "Create or modify artifacts only when the user explicitly asks" in model.received_context
    assert "Engineering/Agents" in model.received_context


async def test_second_turn_replays_history_once_and_does_not_cross_sessions(monkeypatch) -> None:
    model = AssetContextStreamingModel()
    monkeypatch.setattr(
        card_agent, "create_agent_model", lambda _: (AIProviderRuntime(provider="fake", model="test"), model)
    )
    first = agent_session_storage.create(AgentSessionCreate()).id
    other = agent_session_storage.create(AgentSessionCreate()).id
    _ = [
        event
        async for event in card_agent.zett_agent.stream(first, AnalyzeRequest(raw_content="Remember the blue notebook"))
    ]
    _ = [event async for event in card_agent.zett_agent.stream(first, AnalyzeRequest(raw_content="Which notebook?"))]
    assert model.received_context.count("Remember the blue notebook") == 1
    assert model.received_context.count("Which notebook?") == 1
    assert "I used the supplied context." in model.received_context
    _ = [event async for event in card_agent.zett_agent.stream(other, AnalyzeRequest(raw_content="New conversation"))]
    assert "blue notebook" not in model.received_context
    assert "Which notebook?" not in model.received_context


async def test_closing_stream_at_tool_start_records_cancelled_span(monkeypatch) -> None:
    monkeypatch.setattr(
        card_agent,
        "create_agent_model",
        lambda _: (AIProviderRuntime(provider="fake", model="test"), SuccessfulStreamingModel()),
    )
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    stream = card_agent.zett_agent.stream(session_id, request())
    while True:
        name, payload = parse_event(await anext(stream))
        if name == "tool" and payload["state"] == "started":
            break
    await stream.aclose()
    session = agent_session_storage.get(session_id)
    assert session.runs[0].status == AgentRunStatus.CANCELLED
    assert session.runs[0].tool_calls[0].status == AgentRunStatus.CANCELLED
    assert session.artifacts == []

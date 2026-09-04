import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from kcs import config
from kcs.agent import card_agent
from kcs.infra.agent_session_dao import agent_session_storage
from kcs.models import AIProviderRuntime
from kcs.schemas import AgentRunStatus, AgentSessionCreate, AnalysisMessage, AnalyzeRequest, ReasoningEffort

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


class StreamingTestModel(BaseChatModel):
    """Base LangChain chat model used by deterministic KCS Agent tests."""

    calls: int = 0
    tool_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "kcs-test"

    def bind_tools(self, tools: object, **_kwargs: object) -> StreamingTestModel:
        self.tool_names = [tool.name for tool in cast(list[object], tools)]
        return self

    def _generate(self, _messages: list[BaseMessage], **_kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="unused"))])


class SuccessfulStreamingModel(StreamingTestModel):
    """Deterministic two-call model that creates one artifact and then responds."""

    async def _astream(self, _messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        self.calls += 1
        if self.calls == 1:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    additional_kwargs={"reasoning_content": "I should create a structured card."},
                    tool_calls=[
                        {
                            "name": "create_card",
                            "args": {"content": CARD_DRAFT},
                            "id": "tool-1",
                            "type": "tool_call",
                        }
                    ],
                    usage_metadata={
                        "input_tokens": 12,
                        "output_tokens": 8,
                        "total_tokens": 20,
                        "output_token_details": {"reasoning": 3},
                    },
                )
            )
            return
        yield ChatGenerationChunk(message=AIMessageChunk(content="Created "))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="the card.",
                usage_metadata={"input_tokens": 20, "output_tokens": 4, "total_tokens": 24},
                response_metadata={"finish_reason": "stop"},
            )
        )


class FailingStreamingModel(StreamingTestModel):
    """Model that fails during generation."""

    async def _astream(self, _messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        yield ChatGenerationChunk(message=AIMessageChunk(content=""))
        raise RuntimeError("provider stream failed")


class ConversationOnlyStreamingModel(StreamingTestModel):
    """Deterministic model that answers without producing an artifact."""

    async def _astream(self, _messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        yield ChatGenerationChunk(message=AIMessageChunk(content="Let's explore "))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="that idea first.",
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                response_metadata={"finish_reason": "stop"},
            )
        )


class MultipleArtifactStreamingModel(StreamingTestModel):
    """Deterministic model that produces different artifact types in one turn."""

    async def _astream(self, _messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        self.calls += 1
        if self.calls == 1:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "create_card",
                            "args": {"content": CARD_DRAFT},
                            "id": "card-tool",
                            "type": "tool_call",
                        },
                        {
                            "name": "create_article",
                            "args": {"content": ARTICLE_DRAFT},
                            "id": "article-tool",
                            "type": "tool_call",
                        },
                    ],
                )
            )
            return
        yield ChatGenerationChunk(message=AIMessageChunk(content="Created both artifacts."))


class FilesystemStreamingModel(StreamingTestModel):
    """Model that exercises KCS filesystem tools inside a session root."""

    async def _astream(self, _messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        self.calls += 1
        if self.calls == 1:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {"file_path": "/notes/context.md", "content": "Session-only context."},
                            "id": "write-tool",
                            "type": "tool_call",
                        }
                    ],
                )
            )
            return
        yield ChatGenerationChunk(message=AIMessageChunk(content="Stored a private working note."))


class FilesystemTraversalModel(StreamingTestModel):
    """Model that attempts to read beyond the KCS session workspace."""

    async def _astream(self, _messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        self.calls += 1
        if self.calls == 1:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"file_path": "/../outside.txt"},
                            "id": "traversal-tool",
                            "type": "tool_call",
                        }
                    ],
                )
            )
            return
        yield ChatGenerationChunk(message=AIMessageChunk(content="The file is outside my workspace."))


class AssetContextStreamingModel(StreamingTestModel):
    """Model that captures the effective prompt assembled by KCS Agent."""

    received_context: str = ""

    async def _astream(self, messages: list[BaseMessage], **_kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        self.received_context = "\n".join(str(message.content) for message in messages)
        yield ChatGenerationChunk(message=AIMessageChunk(content="I used the supplied context."))


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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (AIProviderRuntime(provider="fake", model="fake-stream"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

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
    assert session.message_count == 3
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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (
            AIProviderRuntime(provider="fake", model="failing-stream"),
            FailingStreamingModel(),
        ),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (
            AIProviderRuntime(provider="fake", model="conversation-only"),
            ConversationOnlyStreamingModel(),
        ),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (
            AIProviderRuntime(provider="fake", model="interruptible"),
            ConversationOnlyStreamingModel(),
        ),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    stream = card_agent.kcs_agent.stream(session_id, request())
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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (AIProviderRuntime(provider="fake", model="multi-output"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (AIProviderRuntime(provider="fake", model="filesystem"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

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
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (AIProviderRuntime(provider="fake", model="filesystem"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: []))
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    outside_file = config.settings.asset_directory / "outside.txt"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("private", encoding="utf-8")

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

    tool_events = [cast(dict[str, object], payload) for name, payload in events if name == "tool"]
    assert tool_events[-1]["name"] == "read_file"
    assert "private" not in json.dumps(tool_events[-1], ensure_ascii=False)


@pytest.mark.asyncio
async def test_kcs_agent_receives_asset_content_and_prompt_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    from kcs.application.services import SessionAssetApplicationService
    from kcs.schemas import SessionTextAssetIn

    model = AssetContextStreamingModel()
    monkeypatch.setattr(
        card_agent,
        "create_chat_model",
        lambda _provider_id, _reasoning_effort: (AIProviderRuntime(provider="fake", model="asset-context"), model),
    )
    monkeypatch.setattr(card_agent.TagApplicationService, "paths", staticmethod(lambda: ["Engineering/Agents"]))
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    SessionAssetApplicationService.create_text(
        session_id,
        SessionTextAssetIn(name="Research note", content="Asset body supplied directly to KCS Agent."),
    )

    events = [parse_event(value) async for value in card_agent.kcs_agent.stream(session_id, request())]

    assert any(name == "result" for name, _ in events)
    assert "Asset body supplied directly to KCS Agent." in model.received_context
    assert "<session_asset_content>" in model.received_context
    assert "untrusted reference data" in model.received_context
    assert "Create or modify artifacts only when the user explicitly asks" in model.received_context
    assert "Engineering/Agents" in model.received_context

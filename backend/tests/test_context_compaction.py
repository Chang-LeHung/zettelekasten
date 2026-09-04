from typing import Any, cast

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from kcs import config
from kcs.agent.compaction import CompactionMiddleware, CompactionOutput, CompactionResult, ModelSnapshotSummarizer
from kcs.application.services import KnowledgeWorkspaceApplicationService
from kcs.infra.agent_session_dao import agent_session_storage
from kcs.infra.context_dao import context_snapshot_storage, raw_log_message_storage
from kcs.models import ContextSnapshotListOptions, RawLogMessageListOptions
from kcs.schemas import AgentMessageRole, AgentSessionCreate, ContextState


class UnusedChatModel(BaseChatModel):
    """Model placeholder because the injected summarizer owns deterministic output."""

    @property
    def _llm_type(self) -> str:
        return "unused"

    def _generate(self, _messages: list[BaseMessage], **_kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="unused"))])


class RecordingSummarizer:
    """Record recursive snapshot inputs and return deterministic structured state."""

    def __init__(self) -> None:
        self.calls: list[tuple[int | None, list[int]]] = []

    async def summarize(self, _model, previous, messages) -> CompactionResult:
        self.calls.append((previous.version if previous else None, [message.sequence for message in messages]))
        return CompactionResult(
            summary=f"Snapshot through {messages[-1].sequence}",
            state=ContextState(goals=["Preserve raw history"], current_plan=["Replay the recent tail"]),
        )


class StructuredCompactionModel:
    """Capture the schema requested by the model-backed snapshot summarizer."""

    def __init__(self) -> None:
        self.schema: type[CompactionOutput] | None = None

    def with_structured_output(self, schema: type[CompactionOutput]) -> StructuredCompactionModel:
        self.schema = schema
        return self

    async def ainvoke(self, _messages: object) -> CompactionOutput:
        return CompactionOutput(summary="Structured snapshot", state=ContextState(facts=["Validated by Pydantic"]))


def append_messages(session_id: str, start: int, end: int) -> None:
    for index in range(start, end + 1):
        agent_session_storage.append_message(
            session_id,
            f"turn-{index}",
            AgentMessageRole.USER if index % 2 else AgentMessageRole.ASSISTANT,
            f"message {index} with enough content to count toward compaction",
        )


@pytest.mark.asyncio
async def test_model_snapshot_summarizer_uses_structured_output() -> None:
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    append_messages(session_id, 1, 2)
    messages = raw_log_message_storage.list(RawLogMessageListOptions(session_id=session_id))
    model = StructuredCompactionModel()

    result = await ModelSnapshotSummarizer().summarize(cast(BaseChatModel, model), None, messages)

    assert model.schema is CompactionOutput
    assert result.summary == "Structured snapshot"
    assert result.state.facts == ["Validated by Pydantic"]


@pytest.mark.asyncio
async def test_compaction_persists_snapshot_and_replays_recent_raw_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "compaction_trigger_tokens", 1)
    monkeypatch.setattr(config.settings, "compaction_recent_messages", 2)
    monkeypatch.setattr(config.settings, "compaction_min_messages", 3)
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    append_messages(session_id, 1, 10)
    summarizer = RecordingSummarizer()

    prepared = await CompactionMiddleware(summarizer).prepare(session_id, UnusedChatModel(), "test", "test-model")

    assert prepared.compacted is True
    assert prepared.snapshot is not None
    assert prepared.snapshot.base_sequence == 8
    assert [message.sequence for message in prepared.messages] == [9, 10]
    assert summarizer.calls == [(None, list(range(1, 9)))]
    raw_log = raw_log_message_storage.list(RawLogMessageListOptions(session_id=session_id))
    assert [message.sequence for message in raw_log] == list(range(1, 11))


@pytest.mark.asyncio
async def test_recursive_compaction_uses_latest_snapshot_and_advances_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "compaction_trigger_tokens", 1)
    monkeypatch.setattr(config.settings, "compaction_recent_messages", 2)
    monkeypatch.setattr(config.settings, "compaction_min_messages", 2)
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    append_messages(session_id, 1, 6)
    summarizer = RecordingSummarizer()
    middleware = CompactionMiddleware(summarizer)
    first = await middleware.prepare(session_id, UnusedChatModel(), "test", "test-model")
    assert first.snapshot is not None
    append_messages(session_id, 7, 10)

    second = await middleware.prepare(session_id, UnusedChatModel(), "test", "test-model")

    assert second.snapshot is not None
    assert second.snapshot.version == 2
    assert second.snapshot.base_sequence == 8
    assert [message.sequence for message in second.messages] == [9, 10]
    assert summarizer.calls == [(None, [1, 2, 3, 4]), (1, [5, 6, 7, 8])]
    snapshots = context_snapshot_storage.list(ContextSnapshotListOptions(session_id=session_id))
    assert [(snapshot.version, snapshot.base_sequence) for snapshot in snapshots] == [(2, 8), (1, 4)]
    assert len(raw_log_message_storage.list(RawLogMessageListOptions(session_id=session_id))) == 10


@pytest.mark.asyncio
async def test_deleting_session_explicitly_removes_raw_log_and_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "compaction_trigger_tokens", 1)
    monkeypatch.setattr(config.settings, "compaction_recent_messages", 2)
    monkeypatch.setattr(config.settings, "compaction_min_messages", 2)
    session_id = agent_session_storage.create(AgentSessionCreate()).id
    append_messages(session_id, 1, 6)
    await CompactionMiddleware(RecordingSummarizer()).prepare(session_id, UnusedChatModel(), "test", "test-model")

    result = KnowledgeWorkspaceApplicationService.delete_session(session_id)

    assert result == {"ok": True}
    assert agent_session_storage.get(session_id) is None
    assert raw_log_message_storage.list(RawLogMessageListOptions(session_id=session_id)) == []
    assert context_snapshot_storage.latest(session_id) is None

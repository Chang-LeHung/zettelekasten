import json
from dataclasses import dataclass
from typing import Protocol

from kcs_agent import AgentModel, SystemMessage, UserMessage
from pydantic import BaseModel, Field

from ..config import settings
from ..domain.context import ContextCompactionPolicy, ContextLogEntry
from ..infra.context_dao import context_snapshot_storage, raw_log_message_storage
from ..infra.structured_output import structured_output
from ..models import RawLogMessageListOptions
from ..schemas import AgentMessageOut, ContextSnapshotCreate, ContextSnapshotOut, ContextState


@dataclass(frozen=True, slots=True)
class CompactionResult:
    """Provider-neutral output produced by a context summarizer."""

    summary: str
    state: ContextState


class CompactionOutput(BaseModel):
    """Schema-enforced model output for one context compaction."""

    summary: str = Field(description="Concise narrative history represented by this checkpoint")
    state: ContextState = Field(description="Updated durable conversation state")


@dataclass(frozen=True, slots=True)
class PreparedContext:
    """Latest snapshot and replay tail used to construct one model request."""

    snapshot: ContextSnapshotOut | None
    messages: list[AgentMessageOut]
    compacted: bool = False


class SnapshotSummarizer(Protocol):
    """Boundary for updating a structured context snapshot."""

    async def summarize(
        self,
        model: AgentModel,
        previous: ContextSnapshotOut | None,
        messages: list[AgentMessageOut],
    ) -> CompactionResult:
        """Summarize previous state plus the next contiguous raw-log segment."""
        ...


class ModelSnapshotSummarizer:
    """Use the selected chat model to update narrative and structured context state."""

    async def summarize(
        self,
        model: AgentModel,
        previous: ContextSnapshotOut | None,
        messages: list[AgentMessageOut],
    ) -> CompactionResult:
        """Request strict JSON and validate it before snapshot persistence."""
        previous_payload = (
            {"summary": previous.summary, "state": previous.state.model_dump(mode="json")} if previous else None
        )
        log_payload = [
            {
                "sequence": message.sequence,
                "role": message.role.value,
                "content": message.content,
                "tool_name": message.tool_name,
            }
            for message in messages
        ]
        prompt = json.dumps(
            {"previous_snapshot": previous_payload, "new_log_messages": log_payload},
            ensure_ascii=False,
        )
        response = await structured_output(
            model,
            CompactionOutput,
            [
                SystemMessage(
                    content="Update a conversation checkpoint from the previous checkpoint and new immutable log entries. Preserve durable facts and decisions, remove repetition, and do not invent details."
                ),
                UserMessage(content=prompt),
            ],
        )
        output = CompactionOutput.model_validate(response)
        return CompactionResult(summary=output.summary, state=output.state)


class CompactionMiddleware:
    """Materialize snapshots before model calls and replay only their raw-log tail."""

    def __init__(self, summarizer: SnapshotSummarizer | None = None) -> None:
        self._summarizer = summarizer or ModelSnapshotSummarizer()

    async def prepare(
        self,
        session_id: str,
        model: AgentModel,
        provider: str | None,
        model_name: str | None,
    ) -> PreparedContext:
        """Compact when over budget, then return latest snapshot plus incremental log replay."""
        snapshot = context_snapshot_storage.latest(session_id)
        base_sequence = snapshot.base_sequence if snapshot else 0
        tail = raw_log_message_storage.list(
            RawLogMessageListOptions(session_id=session_id, after_sequence=base_sequence)
        )
        entries = [ContextLogEntry(message.sequence, message.content) for message in tail]
        snapshot_text = self._snapshot_text(snapshot)
        estimated_tokens = ContextCompactionPolicy.total_tokens(snapshot_text, entries)
        if estimated_tokens < settings.compaction_trigger_tokens:
            return PreparedContext(snapshot=snapshot, messages=tail)

        prefix_entries = ContextCompactionPolicy.compactable_prefix(
            entries,
            settings.compaction_recent_messages,
            settings.compaction_min_messages,
        )
        if not prefix_entries:
            return PreparedContext(snapshot=snapshot, messages=tail)
        boundary = prefix_entries[-1].sequence
        compacted_messages = [message for message in tail if message.sequence <= boundary]
        result = await self._summarizer.summarize(model, snapshot, compacted_messages)
        source_tokens = ContextCompactionPolicy.total_tokens(snapshot_text, prefix_entries)
        snapshot = context_snapshot_storage.create(
            ContextSnapshotCreate(
                session_id=session_id,
                base_sequence=boundary,
                summary=result.summary,
                state=result.state,
                source_message_count=len(compacted_messages),
                source_token_count=source_tokens,
                summary_token_count=ContextCompactionPolicy.estimate_tokens(
                    result.summary + result.state.model_dump_json()
                ),
                provider=provider,
                model=model_name,
            )
        )
        remaining = [message for message in tail if message.sequence > boundary]
        return PreparedContext(snapshot=snapshot, messages=remaining, compacted=True)

    @staticmethod
    def _snapshot_text(snapshot: ContextSnapshotOut | None) -> str:
        if snapshot is None:
            return ""
        return snapshot.summary + snapshot.state.model_dump_json()


compaction_middleware = CompactionMiddleware()

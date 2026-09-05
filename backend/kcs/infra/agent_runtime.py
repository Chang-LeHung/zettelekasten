"""Compose KCS with session persistence implemented by the kcs-agent package."""

from itertools import groupby
from pathlib import Path

from kcs_agent import (
    AgentModel,
    AssistantMessage,
    CompactionExtension,
    RawMessageRecord,
    SessionPersistenceExtension,
    SQLiteSessionStorage,
    ToolGuidelinesExtension,
    ToolMessage,
    UserMessage,
)

from ..config import settings
from ..schemas import AgentMessageOut, AgentMessageRole

_storage: SQLiteSessionStorage | None = None
_storage_path: Path | None = None


def get_agent_runtime_storage() -> SQLiteSessionStorage:
    """Return the package-owned store configured for this KCS process."""
    global _storage, _storage_path
    path = settings.agent_database_path
    if _storage is None or _storage_path != path:
        if _storage is not None:
            _storage.close()
        _storage = SQLiteSessionStorage(path)
        _storage_path = path
    return _storage


def close_agent_runtime_storage() -> None:
    """Dispose the lazily created agent database connection pool."""
    global _storage, _storage_path
    if _storage is not None:
        _storage.close()
    _storage = None
    _storage_path = None


def session_extensions(
    model: AgentModel,
) -> tuple[SessionPersistenceExtension, ToolGuidelinesExtension, CompactionExtension]:
    """Build persistence, prompt, and compaction extensions in lifecycle order."""
    storage = get_agent_runtime_storage()
    return (
        SessionPersistenceExtension(storage),
        ToolGuidelinesExtension(),
        CompactionExtension(
            model,
            max_tokens=settings.agent_context_max_tokens,
            keep_recent_tokens=settings.agent_keep_recent_tokens,
        ),
    )


def list_agent_messages(session_id: str) -> list[AgentMessageOut]:
    """Project each raw request into user and assistant messages for the HTTP API."""
    records = get_agent_runtime_storage().list_raw_messages(session_id)
    messages: list[AgentMessageOut] = []
    for _, request_records in groupby(records, key=lambda record: record.request_id):
        messages.extend(_request_messages(list(request_records)))
    return messages


def _request_messages(records: list[RawMessageRecord]) -> list[AgentMessageOut]:
    """Collapse model/tool loop records while preserving their ordered timeline."""
    result = [_message_out(record) for record in records if isinstance(record.message, UserMessage)]
    assistant_records = [record for record in records if isinstance(record.message, AssistantMessage)]
    if not assistant_records:
        return result

    timeline: list[dict[str, object]] = []
    text = ""
    reasoning = ""
    provider = None
    for record in records:
        match record.message:
            case AssistantMessage() as message:
                if message.reasoning:
                    reasoning += message.reasoning
                    timeline.append({"type": "reasoning", "content": message.reasoning})
                if message.content:
                    text += message.content
                    timeline.append({"type": "message", "content": message.content})
                timeline.extend({"type": "tool", "tool_call_id": call.id} for call in message.tool_calls)
                provider = message.provider or provider
            case ToolMessage():
                pass
            case _:
                pass
    latest = assistant_records[-1]
    result.append(
        AgentMessageOut(
            id=latest.id,
            session_id=latest.session_id,
            turn_id=latest.request_id,
            sequence=latest.sequence,
            role=AgentMessageRole.ASSISTANT,
            content=text,
            reasoning_content=reasoning or None,
            model=None,
            provider=provider,
            tool_name=None,
            metadata={"timeline": timeline},
            created_at=latest.created_at,
        )
    )
    return result


def _message_out(record: RawMessageRecord) -> AgentMessageOut:
    """Project one provider-neutral runtime message without duplicating persistence."""
    message = record.message
    metadata: dict[str, object] = {}
    model = None
    provider = None
    tool_name = None
    reasoning = None
    match message:
        case UserMessage():
            role = AgentMessageRole.USER
            content = message.text
        case AssistantMessage():
            role = AgentMessageRole.ASSISTANT
            content = message.content
            reasoning = message.reasoning
            provider = message.provider
            timeline: list[dict[str, object]] = []
            if message.reasoning:
                timeline.append({"type": "reasoning", "content": message.reasoning})
            timeline.extend({"type": "tool", "tool_call_id": call.id} for call in message.tool_calls)
            if message.content:
                timeline.append({"type": "message", "content": message.content})
            metadata = {"timeline": timeline}
        case ToolMessage():
            role = AgentMessageRole.TOOL
            content = message.content
            tool_name = message.name
            metadata = {"tool_call_id": message.tool_call_id, "success": message.success}
        case _:
            role = AgentMessageRole.SYSTEM
            content = message.content
    return AgentMessageOut(
        id=record.id,
        session_id=record.session_id,
        turn_id=record.request_id,
        sequence=record.sequence,
        role=role,
        content=content,
        reasoning_content=reasoning,
        model=model,
        provider=provider,
        tool_name=tool_name,
        metadata=metadata,
        created_at=record.created_at,
    )

"""Typed projections from zett-agent persistence records to HTTP models."""

from zett_agent.extensions.persistence import (
    RawMessageRecord,
    SessionSummary,
)
from zett_agent.messages import (
    AgentMessage,
    AssistantMessage,
    ToolMessage,
    UserMessage,
)

from ...messages import FrontMessagePart, MessagePartCodec
from ...schemas import session_type_from_code
from ..api.schemas import (
    PersistedMessageOut,
    PersistedToolCallOut,
    SessionOut,
)

_CODEC = MessagePartCodec()


def _message_parts(message: UserMessage | ToolMessage) -> list[FrontMessagePart]:
    """Expose persisted text and images as base64 parts in their stored order."""
    content = message.parts if isinstance(message, UserMessage) else message.content
    return _CODEC.to_front_parts(content)


def message_out(record: RawMessageRecord) -> PersistedMessageOut:
    """Flatten one provider-neutral message without discarding observability."""
    message = record.message
    match message:
        case UserMessage():
            content = message.text
            parts = _message_parts(message)
            reasoning = model = provider = tool_name = None
            tool_calls = []
            tool_call_id = tool_success = None
        case AssistantMessage():
            content = message.content
            parts = []
            reasoning = message.reasoning
            model = message.model
            provider = message.provider
            tool_name = None
            tool_calls = [
                PersistedToolCallOut(id=call.id, name=call.name, arguments=dict(call.arguments))
                for call in message.tool_calls
            ]
            tool_call_id = tool_success = None
        case ToolMessage():
            # Tool images are already restored from SQLite. Keep the public
            # text field textual and expose the original ordered blocks in parts.
            content = message.text
            parts = _message_parts(message)
            reasoning = model = provider = None
            tool_name = message.name
            tool_calls = []
            tool_call_id = message.tool_call_id
            tool_success = message.success
        case AgentMessage():
            content = message.content
            parts = []
            reasoning = model = provider = tool_name = None
            tool_calls = []
            tool_call_id = tool_success = None
        case _:
            content = message.content
            parts = []
            reasoning = model = provider = tool_name = None
            tool_calls = []
            tool_call_id = tool_success = None
    return PersistedMessageOut(
        id=record.id,
        session_id=record.session_id,
        request_id=record.request_id,
        sequence=record.sequence,
        role=message.role,
        content=content,
        parts=parts,
        reasoning_content=reasoning,
        model=model,
        provider=provider,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_success=tool_success,
        attributes=dict(message.attributes),
        metadata=dict(record.metadata),
        tags=dict(record.tags),
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cache_read_tokens=record.cache_read_tokens,
        cache_write_tokens=record.cache_write_tokens,
        reasoning_tokens=record.reasoning_tokens,
        total_tokens=record.total_tokens,
        cache_hit_rate=record.cache_hit_rate,
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_ns=record.duration_ns,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def session_out(summary: SessionSummary) -> SessionOut:
    """Project a lightweight session summary without loading its collections."""
    return SessionOut(
        id=summary.session_id,
        type=session_type_from_code(summary.session_type),
        parent_session_id=summary.parent_session_id,
        agent_name=summary.agent_name,
        title=summary.title,
        message_count=summary.message_count,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )

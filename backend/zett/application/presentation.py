"""Typed projections from zett-agent persistence records to HTTP models."""

from zett_agent import AgentMessage, AssistantMessage, RawMessageRecord, SessionSummary, ToolMessage, UserMessage

from .schemas import PersistedMessageOut, SessionOut


def message_out(record: RawMessageRecord) -> PersistedMessageOut:
    """Flatten one provider-neutral message without discarding observability."""
    message = record.message
    match message:
        case UserMessage():
            content = message.text
            reasoning = model = provider = tool_name = None
        case AssistantMessage():
            content = message.content
            reasoning = message.reasoning
            model = message.model
            provider = message.provider
            tool_name = None
        case ToolMessage():
            content = message.content
            reasoning = model = provider = None
            tool_name = message.name
        case AgentMessage():
            content = message.content
            reasoning = model = provider = tool_name = None
        case _:
            content = message.content
            reasoning = model = provider = tool_name = None
    return PersistedMessageOut(
        id=record.id,
        session_id=record.session_id,
        request_id=record.request_id,
        sequence=record.sequence,
        role=message.role,
        content=content,
        reasoning_content=reasoning,
        model=model,
        provider=provider,
        tool_name=tool_name,
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
        parent_session_id=summary.parent_session_id,
        agent_name=summary.agent_name,
        title=summary.title,
        message_count=summary.message_count,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )

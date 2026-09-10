"""Typed projections from zett-agent persistence records to HTTP models."""

import base64

from zett_agent import (
    AgentMessage,
    AssistantMessage,
    ImageBytesSource,
    ImageContent,
    ImageUrlSource,
    RawMessageRecord,
    SessionSummary,
    TextContent,
    ToolMessage,
    UserMessage,
)

from .schemas import (
    MessageImagePartOut,
    MessagePartOut,
    MessageTextPartOut,
    PersistedMessageOut,
    PersistedToolCallOut,
    SessionOut,
)


def _message_parts(message: UserMessage) -> list[MessagePartOut]:
    """Expose persisted text and images without losing their semantic order."""
    parts: list[MessagePartOut] = []
    for index, part in enumerate(message.parts, start=1):
        if isinstance(part, TextContent):
            parts.append(MessageTextPartOut(text=part.text))
            continue
        if not isinstance(part, ImageContent):
            continue
        name = part.alt_text or f"Pasted image {index}"
        match part.source:
            case ImageBytesSource(data=data, media_type=media_type):
                encoded = base64.b64encode(data).decode("ascii")
                parts.append(
                    MessageImagePartOut(
                        name=name,
                        mime_type=media_type,
                        content_url=f"data:{media_type};base64,{encoded}",
                    )
                )
            case ImageUrlSource(url=url):
                parts.append(MessageImagePartOut(name=name, content_url=url))
    return parts


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
            content = message.content
            parts = []
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
        parent_session_id=summary.parent_session_id,
        agent_name=summary.agent_name,
        title=summary.title,
        message_count=summary.message_count,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )

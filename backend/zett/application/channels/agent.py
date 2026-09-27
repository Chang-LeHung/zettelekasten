"""Contract and Zett bridge for delivering IM turns to the Agent runtime.

The agent contract lives here, not in agim: agim only moves messages in and
out of a platform. How a message becomes an Agent turn is a host concern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field, model_validator
from zett_agent.messages import (
    ImageBytesSource,
    ImageContent,
    TextContent,
    UserContent,
    UserContentPart,
)
from zett_agent.model import (
    ReasoningEffort,
)

from ..._compat import StrEnum
from ...infra.log import get_logger
from ...infra.persistence.dao import provider_storage, session_storage
from ...plugins import ChannelMedia, ChannelMediaKind
from ...schemas import AgentSessionCreate, SessionType
from ..agent.headless import run_headless_prompt
from ..assets.message_files import SessionFileWrite, StoredSessionFile, store_session_files

logger = get_logger(__name__)

#: Largest image handed to the model as image content. Anything bigger stays a
#: session file the model can reach with its own tools.
MAX_INLINE_IMAGE_BYTES = 32 * 1024 * 1024

#: Most image bytes one turn hands the model inline, across all of its images.
MAX_INLINE_IMAGE_TOTAL_BYTES = 64 * 1024 * 1024


class AgentEventKind(StrEnum):
    """Normalized stream events returned by Zett."""

    STARTED = "turn.started"
    DELTA = "message.delta"
    COMPLETED = "message.completed"
    FAILED = "turn.failed"


class AgentTurnRequest(BaseModel):
    """Normalized request sent to the one Zett Agent interaction endpoint."""

    model_config = {"extra": "forbid"}

    request_id: str = Field(min_length=1, max_length=200)
    provider_id: str = Field(min_length=1, max_length=36)
    agent_session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(default="", max_length=100_000)
    media: list[ChannelMedia] = Field(default_factory=list)
    reasoning_effort: str = Field(pattern="^(off|low|medium|high)$")
    allow_coding: bool
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_text_or_media(self) -> AgentTurnRequest:
        """A turn carries something: its text, at least one attachment, or both."""
        if not self.message.strip() and not self.media:
            raise ValueError("Agent turn requires text or media")
        return self


class AgentEvent(BaseModel):
    """One event from the unified Agent turn stream."""

    type: AgentEventKind
    session_id: str | None = None
    content: str | None = None
    error: str | None = None


class AgentClient(ABC):
    """One normalized interface to the Zett Agent application."""

    @abstractmethod
    def stream_turn(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        """Run one turn and yield normalized events."""


class ZettIMAgentClient(AgentClient):
    """Run normalized IM turns through Zett without an HTTP boundary."""

    async def stream_turn(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        """Create or resume a session, then emit normalized Agent events."""
        if await provider_storage.resolve_connection(request.provider_id) is None:
            yield AgentEvent(type=AgentEventKind.FAILED, error="Enabled provider not found")
            return
        session_id = request.agent_session_id
        if session_id is not None and await session_storage.get(session_id) is None:
            # A stored binding outlives its session when the conversation was
            # deleted, and refusing the turn would leave that chat mute forever.
            logger.warning("Bound Agent session is missing; opening a new one; session_id=%s", session_id)
            session_id = None
        if session_id is None:
            title = str(request.metadata.get("channel_name") or "IM conversation")
            session = await session_storage.create(
                AgentSessionCreate(
                    title=f"{title}: {_turn_summary(request)}"[:200],
                    session_type=SessionType.CHANNEL,
                )
            )
            session_id = session.session_id
        yield AgentEvent(type=AgentEventKind.STARTED, session_id=session_id)
        try:
            content = await _turn_content(session_id, request)
            reply = await run_headless_prompt(
                session_id=session_id,
                provider_id=request.provider_id,
                request_id=request.request_id,
                message=request.message,
                content=content,
                reasoning_effort=ReasoningEffort(request.reasoning_effort),
                allow_coding=request.allow_coding,
                metadata={**request.metadata, "source": "im"},
                tags={"source": "im"},
            )
        except Exception as error:
            logger.exception("IM Agent turn failed; request_id=%s session_id=%s", request.request_id, session_id)
            yield AgentEvent(type=AgentEventKind.FAILED, session_id=session_id, error=str(error))
            return
        yield AgentEvent(type=AgentEventKind.COMPLETED, session_id=session_id, content=reply)


def _turn_summary(request: AgentTurnRequest) -> str:
    """Name one conversation by its first text, falling back to its attachments."""
    text = request.message.strip()
    if text:
        return text[:60]
    return " ".join(f"[{item.kind.value}]" for item in request.media)


async def _turn_content(session_id: str, request: AgentTurnRequest) -> UserContent:
    """Build the multimodal model content for one inbound IM turn.

    Images travel as image content so a vision model sees the pixels, and every
    attachment is also written below the session directory so the model can hand
    it to its own tools. Voice, files, video, and oversized images stay file
    references: whether the model can read them is the model's own business.
    """
    if not request.media:
        return request.message
    stored = await store_session_files(
        session_id,
        [SessionFileWrite(name=_media_name(item), mime_type=item.media_type, data=item.data) for item in request.media],
    )
    parts: list[UserContentPart] = []
    if request.message.strip():
        parts.append(TextContent(text=request.message))
    inlined = 0
    for item, written in zip(request.media, stored, strict=True):
        size = len(item.data)
        if (
            item.kind is ChannelMediaKind.IMAGE
            and item.media_type.startswith("image/")
            and 0 < size <= MAX_INLINE_IMAGE_BYTES
            and inlined + size <= MAX_INLINE_IMAGE_TOTAL_BYTES
        ):
            parts.append(
                ImageContent(
                    source=ImageBytesSource(data=item.data, media_type=item.media_type),
                    alt_text=_media_name(item),
                )
            )
            inlined += size
            continue
        parts.append(TextContent(text=_media_reference(item, written)))
    return parts


def _media_name(item: ChannelMedia) -> str:
    """Name one attachment, giving unnamed kinds a usable extension."""
    if item.name:
        return item.name
    suffix = item.media_type.partition("/")[2].split("+")[0]
    return f"{item.kind.value}.{suffix}" if suffix else item.kind.value


def _media_reference(item: ChannelMedia, written: StoredSessionFile | None) -> str:
    """Describe one attachment the model receives as a file rather than as content."""
    location = written.object_key if written is not None else "unsaved"
    return f"[{item.kind.value} attachment saved to {location} ({item.media_type})]"


__all__ = [
    "AgentClient",
    "AgentEvent",
    "AgentEventKind",
    "AgentTurnRequest",
    "MAX_INLINE_IMAGE_BYTES",
    "MAX_INLINE_IMAGE_TOTAL_BYTES",
    "ZettIMAgentClient",
]

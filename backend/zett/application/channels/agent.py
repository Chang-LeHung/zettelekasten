"""Contract and Zett bridge for delivering IM turns to the Agent runtime.

The agent contract lives here, not in agim: agim only moves messages in and
out of a platform. How a message becomes an Agent turn is a host concern.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field
from zett_agent import ReasoningEffort

from ..._compat import StrEnum
from ...infra.log import get_logger
from ...infra.persistence.dao import provider_storage, session_storage
from ...schemas import AgentSessionCreate, SessionType
from ..agent.headless import run_headless_prompt

logger = get_logger(__name__)


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
    message: str = Field(min_length=1, max_length=100_000)
    reasoning_effort: str = Field(pattern="^(off|low|medium|high)$")
    allow_coding: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


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
                    title=f"{title}: {request.message.strip()[:60]}"[:200],
                    session_type=SessionType.CHANNEL,
                )
            )
            session_id = session.session_id
        yield AgentEvent(type=AgentEventKind.STARTED, session_id=session_id)
        try:
            content = await run_headless_prompt(
                session_id=session_id,
                provider_id=request.provider_id,
                request_id=request.request_id,
                message=request.message,
                reasoning_effort=ReasoningEffort(request.reasoning_effort),
                allow_coding=request.allow_coding,
                metadata={**request.metadata, "source": "im"},
                tags={"source": "im"},
            )
        except Exception as error:
            logger.exception("IM Agent turn failed; request_id=%s session_id=%s", request.request_id, session_id)
            yield AgentEvent(type=AgentEventKind.FAILED, session_id=session_id, error=str(error))
            return
        yield AgentEvent(type=AgentEventKind.COMPLETED, session_id=session_id, content=content)


__all__ = [
    "AgentClient",
    "AgentEvent",
    "AgentEventKind",
    "AgentTurnRequest",
    "ZettIMAgentClient",
]

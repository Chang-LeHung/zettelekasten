"""Write models for persisted Agent conversations."""

from pydantic import BaseModel, Field

from .._compat import StrEnum
from .common import NonBlankName200


class SessionType(StrEnum):
    """Application-facing name for a persisted session's origin."""

    NORMAL = "normal"
    SCHEDULED = "scheduled"
    CHANNEL = "channel"


#: Persisted integer codes for ``agent_sessions.session_type``. zett-agent stores
#: the integer and owns neither the names nor their meaning, so the codes and
#: their stories belong to the application.
SESSION_TYPE_TO_CODE = {
    SessionType.NORMAL: 0,
    SessionType.SCHEDULED: 1,
    SessionType.CHANNEL: 2,
}
CODE_TO_SESSION_TYPE = {code: name for name, code in SESSION_TYPE_TO_CODE.items()}


def session_type_from_code(value: int) -> SessionType:
    """Map one persisted integer code to its application-facing name."""
    try:
        return CODE_TO_SESSION_TYPE[value]
    except KeyError as error:
        raise ValueError(f"Unknown session_type code: {value}") from error


class AgentSessionCreate(BaseModel):
    """Complete mutable fields for a persisted Agent conversation."""

    session_type: SessionType = Field(
        default=SessionType.NORMAL,
        description="Origin of the conversation",
    )
    title: NonBlankName200 | None = Field(default=None, description="Optional user-facing conversation title")


class AgentSessionTitleUpdate(BaseModel):
    """Mutable title submitted by a conversation rename action."""

    title: NonBlankName200 = Field(description="New user-facing conversation title")

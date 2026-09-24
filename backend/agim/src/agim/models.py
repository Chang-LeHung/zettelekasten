"""Typed models shared by every agim client."""

from pydantic import BaseModel, ConfigDict, Field

from ._compat import StrEnum, TypeAliasType

JsonValue = TypeAliasType("JsonValue", "str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]")


class LoginStatus(StrEnum):
    """Lifecycle of one QR-assisted login flow."""

    PENDING = "pending"
    SCANNED = "scanned"
    VERIFY_REQUIRED = "verify_required"
    CONNECTED = "connected"
    FAILED = "failed"
    EXPIRED = "expired"


class LoginHandshake(BaseModel):
    """Opaque login state the caller must persist between login and is_login.

    agim never stores anything itself, so the QR payload and whatever provider
    state keeps the poll alive travel back to the caller in this object.
    """

    model_config = ConfigDict(extra="forbid")

    qr_content: str = Field(min_length=1, max_length=10_000)
    qr_url: str | None = Field(default=None, max_length=10_000)
    state: dict[str, JsonValue] = Field(default_factory=dict)


class LoginCredentials(BaseModel):
    """Provider config and secrets returned once a login succeeds."""

    model_config = ConfigDict(extra="forbid")

    config: dict[str, JsonValue] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class LoginState(BaseModel):
    """Current login status; ``is_login`` returns this to its caller."""

    model_config = ConfigDict(extra="forbid")

    status: LoginStatus
    message: str = Field(min_length=1, max_length=2_000)
    credentials: LoginCredentials | None = None


class InboundMessage(BaseModel):
    """One normalized text-bearing inbound message."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(min_length=1, max_length=500)
    user_id: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)
    reply_token: str | None = Field(default=None, max_length=10_000)


class ReceiveResult(BaseModel):
    """One inbound message plus the cursor the caller must persist next."""

    model_config = ConfigDict(extra="forbid")

    message: InboundMessage
    cursor: str = Field(default="", max_length=100_000)


__all__ = [
    "InboundMessage",
    "JsonValue",
    "LoginCredentials",
    "LoginHandshake",
    "LoginState",
    "LoginStatus",
    "ReceiveResult",
]

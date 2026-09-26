"""Typed models shared by every agim client."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._compat import StrEnum, TypeAliasType

JsonValue = TypeAliasType("JsonValue", "str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]")

#: Largest single attachment a platform client keeps in memory.
MAX_MEDIA_BYTES = 256 * 1024 * 1024

#: Most attachments one inbound message may carry.
MAX_MEDIA_ITEMS = 16


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


class MediaKind(StrEnum):
    """Attachment kinds an IM platform can deliver."""

    IMAGE = "image"
    VOICE = "voice"
    FILE = "file"
    VIDEO = "video"


class MediaRejectionReason(StrEnum):
    """Why an attachment did not arrive with its message."""

    TOO_LARGE = "too_large"


class RejectedMedia(BaseModel):
    """One attachment the platform announced but this client refused to carry."""

    model_config = ConfigDict(extra="forbid")

    kind: MediaKind
    reason: MediaRejectionReason


class InboundMedia(BaseModel):
    """One attachment of an inbound message, already downloaded and decrypted.

    Callers receive the bytes so a host can store, forward, or hand them to a
    model; whether a given model can read them is the caller's decision, not
    agim's.
    """

    model_config = ConfigDict(extra="forbid")

    kind: MediaKind
    media_type: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=255)
    data: bytes = Field(min_length=1, max_length=MAX_MEDIA_BYTES)


class InboundMessage(BaseModel):
    """One normalized inbound message: its text plus any attached media."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(min_length=1, max_length=500)
    user_id: str = Field(min_length=1, max_length=500)
    text: str = Field(default="", max_length=100_000)
    media: list[InboundMedia] = Field(default_factory=list, max_length=MAX_MEDIA_ITEMS)
    rejected_media: list[RejectedMedia] = Field(default_factory=list, max_length=MAX_MEDIA_ITEMS)
    reply_token: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def _require_text_or_media(self) -> InboundMessage:
        """A message carries something: text, a delivered attachment, or a refusal."""
        if not self.text.strip() and not self.media and not self.rejected_media:
            raise ValueError("Inbound message requires text, media, or a media rejection")
        return self


class ReceiveResult(BaseModel):
    """One inbound message plus the cursor the caller must persist next."""

    model_config = ConfigDict(extra="forbid")

    message: InboundMessage
    cursor: str = Field(default="", max_length=100_000)


__all__ = [
    "InboundMessage",
    "InboundMedia",
    "JsonValue",
    "LoginCredentials",
    "LoginHandshake",
    "LoginState",
    "LoginStatus",
    "MAX_MEDIA_BYTES",
    "MAX_MEDIA_ITEMS",
    "MediaKind",
    "MediaRejectionReason",
    "RejectedMedia",
    "ReceiveResult",
]

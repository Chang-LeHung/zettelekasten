"""Channel plugin contract and its plugin-facing models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._compat import StrEnum
from .contract import JsonValue, Plugin, PluginKind

#: Largest single attachment a plugin may hand to Zett in one message.
MAX_CHANNEL_MEDIA_BYTES = 256 * 1024 * 1024

#: Most attachments Zett accepts on one inbound message.
MAX_CHANNEL_MEDIA_ITEMS = 16

#: Most attachment bytes Zett accepts on one inbound message.
MAX_CHANNEL_MEDIA_TOTAL_BYTES = 256 * 1024 * 1024


class ChannelLoginStatus(StrEnum):
    """Lifecycle of one QR-assisted channel authorization."""

    PENDING = "pending"
    SCANNED = "scanned"
    VERIFY_REQUIRED = "verify_required"
    CONNECTED = "connected"
    FAILED = "failed"
    EXPIRED = "expired"


class ChannelLoginChallenge(BaseModel):
    """What a plugin returns when a caller begins a login flow."""

    model_config = ConfigDict(extra="forbid")

    qr_content: str = Field(min_length=1, max_length=10_000)
    qr_url: str | None = Field(default=None, max_length=10_000)


class ChannelCredentials(BaseModel):
    """Provider config and secrets returned once a login succeeds."""

    model_config = ConfigDict(extra="forbid")

    config: dict[str, JsonValue] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class ChannelLoginState(BaseModel):
    """Current login status; ``is_login`` returns this to Zett."""

    model_config = ConfigDict(extra="forbid")

    status: ChannelLoginStatus
    message: str = Field(min_length=1, max_length=2_000)
    credentials: ChannelCredentials | None = None


class ChannelMediaKind(StrEnum):
    """Attachment kinds a channel plugin can deliver."""

    IMAGE = "image"
    VOICE = "voice"
    FILE = "file"
    VIDEO = "video"


class ChannelMediaRejectionReason(StrEnum):
    """Why an attachment did not arrive with its message."""

    TOO_LARGE = "too_large"


class ChannelMediaRejection(BaseModel):
    """One attachment the plugin refused to download and deliver."""

    model_config = ConfigDict(extra="forbid")

    kind: ChannelMediaKind
    reason: ChannelMediaRejectionReason


class ChannelMedia(BaseModel):
    """One inbound attachment, already downloaded and decrypted by its plugin.

    Zett stores the bytes and decides what the model receives; a plugin only has
    to deliver them, and whether the configured model can read an image or play
    a voice note is the model's own business.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ChannelMediaKind
    media_type: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=255)
    data: bytes = Field(min_length=1, max_length=MAX_CHANNEL_MEDIA_BYTES)


class ChannelInboundMessage(BaseModel):
    """One normalized inbound message: its text plus any attached media."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(min_length=1, max_length=500)
    user_id: str = Field(min_length=1, max_length=500)
    text: str = Field(default="", max_length=100_000)
    media: list[ChannelMedia] = Field(default_factory=list, max_length=MAX_CHANNEL_MEDIA_ITEMS)
    rejected_media: list[ChannelMediaRejection] = Field(default_factory=list, max_length=MAX_CHANNEL_MEDIA_ITEMS)
    reply_token: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def _require_text_or_media(self) -> ChannelInboundMessage:
        """A message carries something: text, a delivered attachment, or a refusal."""
        if not self.text.strip() and not self.media and not self.rejected_media:
            raise ValueError("Inbound channel message requires text, media, or a media rejection")
        return self


class ChannelPlugin(Plugin, ABC):
    """One IM platform integration registered into Zett."""

    kind: ClassVar[PluginKind] = PluginKind.CHANNEL

    @abstractmethod
    async def login(self) -> ChannelLoginChallenge:
        """Begin a login flow and return the QR payload for the browser."""

    @abstractmethod
    async def is_login(self) -> ChannelLoginState:
        """Return the current login state; callers poll this until it settles."""

    async def submit_login_code(self, code: str) -> None:
        """Record a user-supplied verification code for the active login flow.

        Platforms without a verification step keep the default no-op so callers
        never need to know whether the current plugin uses one.
        """
        return None

    @abstractmethod
    async def receive(self) -> ChannelInboundMessage:
        """Await the next inbound message."""

    @abstractmethod
    async def send(self, chat_id: str, text: str) -> None:
        """Send one outbound message."""


__all__ = [
    "ChannelCredentials",
    "ChannelMedia",
    "ChannelMediaKind",
    "ChannelMediaRejection",
    "ChannelMediaRejectionReason",
    "ChannelInboundMessage",
    "ChannelLoginChallenge",
    "ChannelLoginState",
    "ChannelLoginStatus",
    "ChannelPlugin",
    "MAX_CHANNEL_MEDIA_BYTES",
    "MAX_CHANNEL_MEDIA_ITEMS",
    "MAX_CHANNEL_MEDIA_TOTAL_BYTES",
]

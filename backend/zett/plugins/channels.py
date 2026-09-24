"""Channel plugin contract and its plugin-facing models."""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .._compat import StrEnum
from .contract import JsonValue, Plugin, PluginKind


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


class ChannelInboundMessage(BaseModel):
    """One normalized text-bearing inbound message."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=200)
    chat_id: str = Field(min_length=1, max_length=500)
    user_id: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)
    reply_token: str | None = Field(default=None, max_length=10_000)


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
    "ChannelInboundMessage",
    "ChannelLoginChallenge",
    "ChannelLoginState",
    "ChannelLoginStatus",
    "ChannelPlugin",
]

"""Public channel DTOs proxied between Zett and the standalone IM gateway."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from zett_agent import ReasoningEffort

from ..plugins import ChannelLoginStatus
from .common import JsonValue, NonBlankName100


class ChannelType(StrEnum):
    """Supported remote chat platform."""

    WECHAT = "wechat"


class ChannelUpdate(BaseModel):
    """Partial channel mutation accepted by the Zett management API."""

    model_config = ConfigDict(extra="forbid")

    name: NonBlankName100 | None = None
    provider_id: str | None = Field(default=None, min_length=1, max_length=36)
    enabled: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    allow_coding: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> ChannelUpdate:
        """Reject empty patches."""
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one channel field must be supplied")
        return self


class Channel(BaseModel):
    """Public channel metadata returned by the IM gateway."""

    id: str
    name: str
    channel_type: ChannelType
    provider_id: str
    enabled: bool
    reasoning_effort: ReasoningEffort
    allow_coding: bool
    config: dict[str, JsonValue]
    secret_keys: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ChannelLoginStart(BaseModel):
    """Request one QR authorization flow through the IM gateway."""

    model_config = ConfigDict(extra="forbid")

    channel_type: ChannelType = ChannelType.WECHAT
    provider_id: str = Field(min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=100)


class ChannelLogin(BaseModel):
    """One pending or completed channel authorization."""

    id: str
    channel_type: ChannelType = ChannelType.WECHAT
    provider_id: str
    name: str | None
    status: ChannelLoginStatus
    qr_url: str | None = None
    qr_data_url: str | None = None
    message: str | None = None
    channel_id: str | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


__all__ = [
    "Channel",
    "ChannelLogin",
    "ChannelLoginStart",
    "ChannelLoginStatus",
    "ChannelType",
    "ChannelUpdate",
]

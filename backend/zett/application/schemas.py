"""HTTP application request and response models."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..schemas import (
    AgentArtifact,
    ArtifactContent,
    ArtifactCreateContent,
    ArtifactStatus,
    ProviderType,
    SessionAssetOut,
)


class DeleteResponse(BaseModel):
    """Result of an idempotent HTTP deletion."""

    ok: bool


class PersistedToolCallOut(BaseModel):
    """One complete tool invocation selected by an Assistant message."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MessageTextPartOut(BaseModel):
    """One text segment in an ordered persisted user message."""

    type: Literal["text"] = "text"
    text: str


class MessageImagePartOut(BaseModel):
    """One image segment in an ordered persisted user or tool message."""

    type: Literal["image"] = "image"
    name: str
    mime_type: str | None = None
    content_url: str


MessagePartOut = Annotated[MessageTextPartOut | MessageImagePartOut, Field(discriminator="type")]


class PersistedMessageOut(BaseModel):
    """One immutable raw message projected for the conversation UI."""

    id: str
    session_id: str
    request_id: str
    sequence: int
    role: str
    content: str
    parts: list[MessagePartOut] = Field(default_factory=list)
    reasoning_content: str | None = None
    model: str | None = None
    provider: str | None = None
    tool_calls: list[PersistedToolCallOut] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_success: bool | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    cache_hit_rate: float | None = None
    started_at: datetime
    completed_at: datetime
    duration_ns: int
    created_at: datetime
    updated_at: datetime


class SessionOut(BaseModel):
    """Session metadata optionally enriched with UI workspace data."""

    id: str
    parent_session_id: str | None = None
    agent_name: str | None = None
    title: str | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime
    messages: list[PersistedMessageOut] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    assets: list[SessionAssetOut] = Field(default_factory=list)


class AgentStartOut(BaseModel):
    """New empty conversation and its initial workspace collections."""

    conversation_id: str
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    assets: list[SessionAssetOut] = Field(default_factory=list)


class ArtifactCreateIn(BaseModel):
    """New draft or saved artifact scoped by the URL session."""

    content: ArtifactCreateContent
    raw_content: str | None = None
    status: ArtifactStatus = ArtifactStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactUpdateIn(BaseModel):
    """Replacement artifact content."""

    content: ArtifactContent


class TagCreateIn(BaseModel):
    """Create one persistent hierarchical library tag."""

    path: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1_000)
    color: str | None = Field(default=None, max_length=32)


class TagUpdateIn(BaseModel):
    """Update the path or presentation metadata of one leaf tag."""

    path: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=1_000)
    color: str | None = Field(default=None, max_length=32)


class ArtifactTagsIn(BaseModel):
    """Complete replacement set of confirmed tag paths for an artifact."""

    paths: list[str] = Field(default_factory=list, max_length=100)


class TextAssetIn(BaseModel):
    """Inline text asset submitted by the composer."""

    name: str = Field(min_length=1, max_length=500)
    content: str
    mime_type: str = Field(default="text/plain", max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkAssetIn(BaseModel):
    """External link attached to a conversation."""

    name: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderIn(BaseModel):
    """Provider settings accepted from the browser preferences form."""

    name: str = Field(min_length=1, max_length=100)
    provider: ProviderType
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    response: bool = Field(default=False, description="Use a Responses API endpoint instead of chat completions")
    enabled: bool = True

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        """Accept UI labels while persisting canonical provider enum values."""
        aliases = {
            "openai-compatible": "openai_compatible",
            "response-compatible": "responses_compatible",
            "responses-compatible": "responses_compatible",
            "gemini": "google",
        }
        return aliases.get(str(value), value)

    @field_validator("base_url", "api_key", mode="before")
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def responses_api_requires_compatible_provider(self) -> ProviderIn:
        """Reject a Responses mode that the selected native adapter cannot use."""
        supported = {
            ProviderType.OPENAI,
            ProviderType.OPENAI_COMPATIBLE,
            ProviderType.RESPONSES_COMPATIBLE,
            ProviderType.DEEPSEEK,
        }
        if self.provider == ProviderType.RESPONSES_COMPATIBLE:
            if not self.base_url:
                raise ValueError("Responses-compatible providers require a base URL")
            self.response = True
        if self.response and self.provider not in supported:
            raise ValueError(f"Responses API is not supported by {self.provider.value}")
        return self


class ProviderResponse(BaseModel):
    """Safe provider settings; credentials are never returned."""

    id: str
    name: str
    provider: ProviderType
    model: str
    base_url: str | None
    api_key_configured: bool
    temperature: float | None = None
    response: bool = False
    enabled: bool
    created_at: datetime
    updated_at: datetime


class MessageTextPartIn(BaseModel):
    """One text segment in an ordered multimodal request."""

    type: Literal["text"] = "text"
    text: str


class MessageImagePartIn(BaseModel):
    """One base64-encoded image segment in an ordered multimodal request."""

    type: Literal["image"] = "image"
    name: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(pattern=r"^image/[A-Za-z0-9.+-]+$", max_length=255)
    data_base64: str = Field(min_length=1)


MessagePartIn = Annotated[MessageTextPartIn | MessageImagePartIn, Field(discriminator="type")]


class UserMessageIn(BaseModel):
    """One multimodal user message shared by starts and active steering."""

    raw_content: str = ""
    # Up to 256 configured images may be interleaved with 257 text segments.
    parts: list[MessagePartIn] = Field(default_factory=list, max_length=513)

    @property
    def current_message(self) -> str:
        """Return only this request's text; persisted history is restored separately."""
        return self.raw_content.strip()

    @model_validator(mode="after")
    def require_message_content(self) -> AnalyzeRequest:
        """Accept text, images, or both while rejecting an empty user turn."""
        if not self.current_message and not any(
            isinstance(part, MessageImagePartIn) or (isinstance(part, MessageTextPartIn) and part.text.strip())
            for part in self.parts
        ):
            raise ValueError("A message requires text or at least one image")
        return self


class AnalyzeRequest(UserMessageIn):
    """One user turn sent to the Zettelkasten Agent."""

    provider_id: str
    reasoning_effort: str = "medium"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, Any] = Field(default_factory=dict)


class ExternalEventIn(BaseModel):
    """External UI event delivered to extensions of one active request."""

    name: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExternalEventOut(BaseModel):
    """Extensions that accepted an external event."""

    accepted: bool
    accepted_by: list[str] = Field(default_factory=list)


class SteerRequest(UserMessageIn):
    """One urgent message delivered to the active Agent request."""

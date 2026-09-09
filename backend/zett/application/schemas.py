"""HTTP application request and response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..schemas import AgentArtifact, ArtifactContent, ArtifactStatus, ProviderType, SessionAssetOut


class DeleteResponse(BaseModel):
    """Result of an idempotent HTTP deletion."""

    ok: bool


class PersistedMessageOut(BaseModel):
    """One immutable raw message projected for the conversation UI."""

    id: str
    session_id: str
    request_id: str
    sequence: int
    role: str
    content: str
    reasoning_content: str | None = None
    model: str | None = None
    provider: str | None = None
    tool_name: str | None = None
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

    content: ArtifactContent
    raw_content: str | None = None
    status: ArtifactStatus = ArtifactStatus.DRAFT
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactUpdateIn(BaseModel):
    """Replacement artifact content."""

    content: ArtifactContent


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
    enabled: bool = True

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        """Accept UI labels while persisting canonical provider enum values."""
        aliases = {"openai-compatible": "openai_compatible", "gemini": "google"}
        return aliases.get(str(value), value)

    @field_validator("base_url", "api_key", mode="before")
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        return None if value == "" else value


class ProviderResponse(BaseModel):
    """Safe provider settings; credentials are never returned."""

    id: str
    name: str
    provider: ProviderType
    model: str
    base_url: str | None
    api_key_configured: bool
    temperature: float | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AnalyzeRequest(BaseModel):
    """One user turn sent to the Zettelkasten Agent."""

    raw_content: str = Field(min_length=1)
    provider_id: str
    reasoning_effort: str = "medium"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, Any] = Field(default_factory=dict)

    @property
    def current_message(self) -> str:
        """Use the last UI user turn when refining, otherwise the initial text."""
        for message in reversed(self.messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                content = str(message["content"]).strip()
                if content:
                    return content
        return self.raw_content.strip()


class ExternalEventIn(BaseModel):
    """External UI event delivered to extensions of one active request."""

    name: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExternalEventOut(BaseModel):
    """Extensions that accepted an external event."""

    accepted: bool
    accepted_by: list[str] = Field(default_factory=list)

"""HTTP application request and response models."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..messages import FrontMessagePart, FrontUserMessage
from ..schemas import (
    AgentArtifactEntity,
    ArtifactContent,
    ArtifactCreateContent,
    ArtifactStatus,
    ProviderType,
    SessionAssetEntity,
)


class DeleteResponse(BaseModel):
    """Result of an idempotent HTTP deletion."""

    ok: bool


class UsageActivityDayOut(BaseModel):
    """One UTC day in the model usage activity chart."""

    date: date
    requests: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    total_tokens: int


class ModelUsageActivitySeriesOut(BaseModel):
    """Daily request and token activity for one provider model."""

    provider: str | None = None
    model: str | None = None
    days: list[UsageActivityDayOut]


class PersistedToolCallOut(BaseModel):
    """One complete tool invocation selected by an Assistant message."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class PersistedMessageOut(BaseModel):
    """One immutable raw message projected for the conversation UI."""

    id: str
    session_id: str
    request_id: str
    sequence: int
    role: str
    content: str
    parts: list[FrontMessagePart] = Field(default_factory=list)
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
    artifacts: list[AgentArtifactEntity] = Field(default_factory=list)
    assets: list[SessionAssetEntity] = Field(default_factory=list)


class AgentStartOut(BaseModel):
    """New empty conversation and its initial workspace collections."""

    conversation_id: str
    artifacts: list[AgentArtifactEntity] = Field(default_factory=list)
    assets: list[SessionAssetEntity] = Field(default_factory=list)


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
    """Safe provider settings for lists and write acknowledgements."""

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


class ProviderDetailResponse(ProviderResponse):
    """One provider configuration with its decrypted key for local editing."""

    api_key: str | None = Field(
        default=None,
        repr=False,
        description="Decrypted API key returned only by the single-provider settings endpoint",
    )


class UserMessageIn(FrontUserMessage):
    """One multimodal user message shared by starts and active steering."""


class AnalyzeRequest(UserMessageIn):
    """One user turn sent to the Zettelkasten Agent."""

    provider_id: str
    reasoning_effort: str = "medium"
    shell_approval_mode: Literal["review", "allow_all"] = "review"
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


class SlashCommandOut(BaseModel):
    """Browser-safe metadata for one container-registered slash command."""

    id: str
    name: str
    description: str
    type: str


class AtCommandOut(BaseModel):
    """Browser-safe metadata for one resource the conversation may reference."""

    id: str
    kind: str
    name: str
    label: str
    description: str


class ShellApprovalSettings(BaseModel):
    """Persisted shell approval policy for one Agent session."""

    mode: Literal["review", "allow_all"] = "review"


class SteerRequest(UserMessageIn):
    """One urgent message delivered to the active Agent request."""

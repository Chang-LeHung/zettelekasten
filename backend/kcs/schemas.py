from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class CardType(StrEnum):
    """Supported knowledge card categories."""

    NOTE = "note"
    IDEA = "idea"
    QUOTE = "quote"
    TODO = "todo"
    REFERENCE = "reference"


def normalize_card_type(value: object) -> CardType:
    """Map common model-generated category names to a supported card type."""
    if isinstance(value, CardType):
        return value
    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "knowledge": CardType.NOTE,
        "article": CardType.NOTE,
        "document": CardType.NOTE,
        "insight": CardType.NOTE,
        "concept": CardType.NOTE,
        "thought": CardType.IDEA,
        "brainstorm": CardType.IDEA,
        "suggestion": CardType.IDEA,
        "task": CardType.TODO,
        "action": CardType.TODO,
        "action_item": CardType.TODO,
        "citation": CardType.QUOTE,
        "excerpt": CardType.QUOTE,
        "link": CardType.REFERENCE,
        "resource": CardType.REFERENCE,
    }
    try:
        return CardType(normalized)
    except ValueError:
        return aliases.get(normalized, CardType.NOTE)


class TagCreate(BaseModel):
    """Input fields used to create or update a hierarchical tag."""

    name: str = Field(min_length=1, max_length=100, description="Display name of the tag")
    parent_id: int | None = Field(default=None, description="Parent tag ID; null creates a root tag")
    description: str | None = Field(default=None, description="Optional explanation of the tag")
    color: str | None = Field(default=None, description="Optional CSS color or hex color")


class TagOut(TagCreate):
    """Serialized tag including its computed path and nested children."""

    id: int = Field(description="Database ID of the tag")
    created_at: datetime = Field(description="UTC creation timestamp")
    path: str = Field(description="Full hierarchical path, such as Technology/Python")
    card_count: int = Field(default=0, description="Number of directly linked cards")
    children: list[TagOut] = Field(default_factory=list, description="Direct child tags")


class CardCreate(BaseModel):
    """Input fields used to create or update a knowledge card."""

    type: CardType = Field(default=CardType.NOTE, description="Normalized card category")
    title: str = Field(description="Short human-readable card title")
    content: str = Field(description="Normalized card body; Markdown is supported by convention")
    raw_content: str | None = Field(default=None, description="Original unmodified user input")
    summary: str | None = Field(default=None, description="Optional short summary")
    source: str | None = Field(default=None, description="Optional source, URL, book, or person")
    tag_ids: list[int] = Field(default_factory=list, description="IDs of tags linked to this card")

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> CardType:
        return normalize_card_type(value)


class CardOut(CardCreate):
    """Serialized card including lifecycle metadata and resolved tags."""

    id: str = Field(description="Stable UUID of the card")
    status: str = Field(description="Lifecycle status, currently active")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")
    tags: list[TagOut] = Field(default_factory=list, description="Resolved tag objects")


class ArticleStatus(StrEnum):
    """Lifecycle states for permanent library articles."""

    ACTIVE = "active"


class ArticleCreate(BaseModel):
    """Input fields used to create or update a permanent Markdown article."""

    title: str = Field(description="Human-readable article title")
    subtitle: str = Field(default="", description="Optional article subtitle")
    summary: str = Field(default="", description="Short article abstract")
    content: str = Field(description="Complete article body in Markdown")
    raw_content: str | None = Field(default=None, description="Original input associated with the article")
    tag_paths: list[str] = Field(default_factory=list, description="Selected hierarchical tag paths")


class ArticleOut(ArticleCreate):
    """Serialized permanent article including lifecycle metadata."""

    id: str = Field(description="Stable UUID of the article")
    status: ArticleStatus = Field(description="Article lifecycle status")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


class LibraryItemType(StrEnum):
    """Permanent resource kinds displayed by the unified knowledge library."""

    CARD = "card"
    ARTICLE = "article"


class LibraryItemOut(BaseModel):
    """Normalized read model shared by card and article library entries."""

    id: str = Field(description="Stable resource UUID")
    item_type: LibraryItemType = Field(description="Permanent resource kind")
    title: str = Field(description="Human-readable resource title")
    subtitle: str | None = Field(default=None, description="Article subtitle when applicable")
    summary: str | None = Field(default=None, description="Short resource summary")
    content: str = Field(description="Complete Markdown body")
    raw_content: str | None = Field(default=None, description="Original input associated with the resource")
    source: str | None = Field(default=None, description="Card source when applicable")
    card_type: CardType | None = Field(default=None, description="Card category when applicable")
    status: str = Field(description="Resource lifecycle status")
    tag_paths: list[str] = Field(default_factory=list, description="Resolved hierarchical tag paths")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


class LibraryItemUpdate(BaseModel):
    """Editable fields shared by permanent card and article resources."""

    title: str = Field(min_length=1, description="Updated resource title")
    subtitle: str | None = Field(default=None, description="Updated article subtitle when applicable")
    summary: str | None = Field(default=None, description="Updated resource summary")
    content: str = Field(min_length=1, description="Updated Markdown body")


class SuggestedTag(BaseModel):
    """AI-proposed tag that requires user confirmation before saving."""

    path: str = Field(description="Hierarchical tag path")
    existing: bool = Field(description="Whether the path already exists")
    confidence: float = Field(default=0, ge=0, le=1, description="Model confidence from 0 to 1")
    reason: str | None = Field(default=None, description="Short reason for the recommendation")


class ArtifactType(StrEnum):
    """Kinds of durable outputs that a KCS Agent session may produce."""

    CARD = "card"
    ARTICLE = "article"
    IMAGE = "image"


class ArtifactStatus(StrEnum):
    """Lifecycle states shared by every session artifact."""

    DRAFT = "draft"
    SAVED = "saved"


class ArtifactContentBase(BaseModel):
    """Fields shared by all editable session artifact content."""

    title: str = Field(description="User-facing artifact title")
    summary: str = Field(default="", description="Generated summary")
    suggested_tags: list[SuggestedTag] = Field(default_factory=list, description="Suggested tags")
    keywords: list[str] = Field(default_factory=list, description="Extracted keywords")


class CardArtifactContent(ArtifactContentBase):
    """Editable content for a knowledge-card artifact."""

    artifact_type: Literal[ArtifactType.CARD] = ArtifactType.CARD
    card_type: CardType = Field(default=CardType.NOTE, description="Normalized knowledge card category")
    content: str = Field(description="Card body in Markdown")

    @field_validator("card_type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> CardType:
        return normalize_card_type(value)


class ArticleArtifactContent(ArtifactContentBase):
    """Editable content for a long-form Markdown article."""

    artifact_type: Literal[ArtifactType.ARTICLE] = ArtifactType.ARTICLE
    subtitle: str = Field(default="", description="Optional article subtitle")
    content: str = Field(description="Long-form article body in Markdown")


class ImageArtifactContent(ArtifactContentBase):
    """Editable description and location for an image artifact."""

    artifact_type: Literal[ArtifactType.IMAGE] = ArtifactType.IMAGE
    prompt: str = Field(default="", description="Prompt or creative direction used for the image")
    alt_text: str = Field(default="", description="Accessible description of the image")
    source_url: str | None = Field(default=None, description="External image URL when the image is remote")
    asset_id: str | None = Field(default=None, description="Session asset ID when the image is stored locally")


ArtifactContent = Annotated[
    CardArtifactContent | ArticleArtifactContent | ImageArtifactContent,
    Field(discriminator="artifact_type"),
]


class AgentArtifactWrite(BaseModel):
    """Complete write model accepted by the session artifact storage boundary."""

    session_id: str = Field(description="Owning agent session UUID")
    content: ArtifactContent = Field(description="Type-specific editable artifact content")
    raw_content: str | None = Field(default=None, description="Original input associated with this artifact")
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT, description="Current artifact lifecycle state")
    linked_resource_id: str | None = Field(default=None, description="Permanent resource ID after publication")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible artifact metadata")


class AgentArtifact(BaseModel):
    """One typed output produced inside a persisted agent conversation."""

    id: str = Field(description="Stable artifact UUID")
    session_id: str = Field(description="Owning agent session UUID")
    artifact_type: ArtifactType = Field(description="Artifact discriminator used for rendering and queries")
    status: ArtifactStatus = Field(description="Current artifact lifecycle state")
    content: ArtifactContent = Field(description="Type-specific editable artifact content")
    raw_content: str | None = Field(default=None, description="Original input associated with this artifact")
    linked_resource_id: str | None = Field(default=None, description="Permanent resource ID after publication")
    version: int = Field(default=1, ge=1, description="Monotonic revision number")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible artifact metadata")
    created_at: datetime = Field(description="UTC artifact creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


class AgentSessionStatus(StrEnum):
    """Lifecycle states for a persisted KCS Agent conversation."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class AgentMessageRole(StrEnum):
    """Supported roles for persisted conversation messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AgentRunStatus(StrEnum):
    """Execution states for an observable agent turn."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReasoningEffort(StrEnum):
    """User-selectable reasoning intensity for providers that support it."""

    OFF = "off"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SessionAssetType(StrEnum):
    """Supported asset categories within a persisted agent session."""

    TEXT = "text"
    IMAGE = "image"
    LINK = "link"
    FILE = "file"


class SessionAssetCreate(BaseModel):
    """Complete write model consumed by the session asset storage adapter."""

    session_id: str = Field(description="Owning session UUID")
    asset_type: SessionAssetType = Field(description="Asset storage and rendering category")
    name: str = Field(min_length=1, max_length=500, description="User-facing asset name")
    mime_type: str | None = Field(default=None, max_length=255, description="IANA media type when known")
    content: bytes | None = Field(default=None, exclude=True, repr=False, description="Binary file payload")
    text_content: str | None = Field(default=None, description="Inline text asset content")
    source_url: str | None = Field(default=None, description="External URL represented by a link asset")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class SessionTextAssetIn(BaseModel):
    """HTTP input used to attach text to a session."""

    name: str = Field(min_length=1, max_length=500, description="User-facing text asset name")
    content: str = Field(description="UTF-8 text stored inline in SQLite")
    mime_type: str = Field(default="text/plain", max_length=255, description="Text media type")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class SessionLinkAssetIn(BaseModel):
    """HTTP input used to attach an external link to a session."""

    name: str = Field(min_length=1, max_length=500, description="User-facing link name")
    url: str = Field(min_length=1, description="External resource URL")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class SessionAssetOut(BaseModel):
    """Serialized session asset with a controlled content endpoint."""

    id: str = Field(description="Stable asset UUID")
    session_id: str = Field(description="Owning session UUID")
    asset_type: SessionAssetType = Field(description="Asset storage and rendering category")
    name: str = Field(description="User-facing asset name")
    mime_type: str | None = Field(default=None, description="IANA media type when known")
    size_bytes: int = Field(default=0, description="Stored payload size in bytes")
    sha256: str | None = Field(default=None, description="SHA-256 digest of stored content")
    text_content: str | None = Field(default=None, description="Inline text content for text assets")
    source_url: str | None = Field(default=None, description="External URL for link assets")
    content_url: str | None = Field(default=None, description="Application URL for reading stored content")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


class AgentSessionCreate(BaseModel):
    """Fields used to create a persisted KCS Agent conversation."""

    title: str | None = Field(default=None, description="Optional user-facing conversation title")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible session metadata")


class AgentSessionTitleUpdate(BaseModel):
    """User-authored replacement for a conversation display title."""

    title: str = Field(min_length=1, max_length=100, description="Stable user-facing conversation title")


class AgentMessageOut(BaseModel):
    """One immutable raw-log message in a KCS Agent conversation."""

    id: str = Field(description="Stable message UUID")
    session_id: str = Field(description="Owning session UUID")
    turn_id: str = Field(description="Agent turn UUID")
    sequence: int = Field(description="Monotonic message position within the session")
    role: AgentMessageRole = Field(description="Message author role")
    content: str = Field(description="Persisted message text")
    reasoning_content: str | None = Field(default=None, description="Provider-supplied reasoning text")
    model: str | None = Field(default=None, description="Model associated with assistant output")
    provider: str | None = Field(default=None, description="Provider associated with assistant output")
    tool_name: str | None = Field(default=None, description="Tool name for tool-role messages")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible message metadata")
    created_at: datetime = Field(description="UTC message creation timestamp")


class RawLogMessageCreate(BaseModel):
    """Write model for appending one immutable event to a session message log."""

    session_id: str = Field(description="Owning session UUID")
    turn_id: str = Field(description="Agent turn UUID")
    role: AgentMessageRole = Field(description="Message author role")
    content: str = Field(description="Complete persisted event content")
    model: str | None = Field(default=None, description="Model associated with assistant output")
    provider: str | None = Field(default=None, description="Provider associated with assistant output")
    tool_name: str | None = Field(default=None, description="Tool name for tool-role messages")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible event metadata")


class ContextState(BaseModel):
    """Structured durable state retained across recursive context compactions."""

    goals: list[str] = Field(default_factory=list, description="Current user goals")
    preferences: list[str] = Field(default_factory=list, description="Stable user preferences and constraints")
    decisions: list[str] = Field(default_factory=list, description="Decisions already made in the conversation")
    facts: list[str] = Field(default_factory=list, description="Important established facts")
    files: list[str] = Field(default_factory=list, description="Relevant session-relative files and assets")
    current_plan: list[str] = Field(default_factory=list, description="Current execution or discussion plan")
    open_questions: list[str] = Field(default_factory=list, description="Unresolved questions and blockers")


class ContextSnapshotCreate(BaseModel):
    """Write model for one versioned materialized conversation context."""

    session_id: str = Field(description="Owning session UUID")
    base_sequence: int = Field(ge=1, description="Highest raw-log sequence represented by this snapshot")
    summary: str = Field(description="Compact narrative history through the base sequence")
    state: ContextState = Field(default_factory=ContextState, description="Structured durable conversation state")
    source_message_count: int = Field(ge=1, description="Number of new raw events consumed by this compaction")
    source_token_count: int = Field(ge=0, description="Estimated tokens consumed by this compaction")
    summary_token_count: int = Field(ge=0, description="Estimated tokens in the resulting snapshot")
    provider: str | None = Field(default=None, description="Provider used to generate the snapshot")
    model: str | None = Field(default=None, description="Model used to generate the snapshot")


class ContextSnapshotOut(ContextSnapshotCreate):
    """Read model for an immutable, versioned context snapshot."""

    id: str = Field(description="Stable snapshot UUID")
    version: int = Field(ge=1, description="Monotonic snapshot version within the session")
    created_at: datetime = Field(description="UTC snapshot creation timestamp")


class AgentToolCallOut(BaseModel):
    """Observable record for one tool execution inside an agent run."""

    id: str = Field(description="Provider tool-call ID or generated UUID")
    run_id: str = Field(description="Owning agent run UUID")
    session_id: str = Field(description="Owning session UUID")
    tool_name: str = Field(description="Executed LangChain tool name")
    status: AgentRunStatus = Field(description="Tool execution status")
    input: dict[str, object] = Field(default_factory=dict, description="Validated tool arguments")
    output: object | None = Field(default=None, description="Serialized tool result")
    duration_ms: float | None = Field(default=None, description="Tool wall-clock duration in milliseconds")
    error_message: str | None = Field(default=None, description="Captured tool failure message")
    started_at: datetime = Field(description="UTC tool start timestamp")
    ended_at: datetime | None = Field(default=None, description="UTC tool completion timestamp")


class AgentRunOut(BaseModel):
    """Metrics and trace data for one user-to-agent turn."""

    id: str = Field(description="Stable run UUID")
    trace_id: str = Field(description="Trace identifier shared by related spans")
    span_id: str = Field(description="Root span identifier for this run")
    session_id: str = Field(description="Owning session UUID")
    turn_id: str = Field(description="Conversation turn UUID")
    agent_name: str = Field(description="Agent implementation name")
    status: AgentRunStatus = Field(description="Run execution status")
    provider_id: int | None = Field(default=None, description="Selected local provider configuration ID")
    provider: str | None = Field(default=None, description="Provider protocol identifier")
    model: str | None = Field(default=None, description="Requested model identifier")
    reasoning_effort: ReasoningEffort = Field(description="Requested provider reasoning intensity")
    started_at: datetime = Field(description="UTC run start timestamp")
    first_token_at: datetime | None = Field(default=None, description="UTC timestamp of the first streamed token")
    ended_at: datetime | None = Field(default=None, description="UTC run completion timestamp")
    total_duration_ms: float | None = Field(default=None, description="Complete turn wall-clock duration")
    time_to_first_token_ms: float | None = Field(default=None, description="Latency before the first streamed token")
    generation_duration_ms: float | None = Field(default=None, description="Time from first token to model completion")
    reasoning_duration_ms: float | None = Field(default=None, description="Time spent streaming provider reasoning")
    tool_duration_ms: float = Field(default=0, description="Cumulative tool execution duration")
    input_tokens: int = Field(default=0, description="Prompt tokens including cached input")
    output_tokens: int = Field(default=0, description="Generated completion tokens")
    reasoning_tokens: int = Field(default=0, description="Provider-reported reasoning tokens")
    cache_read_tokens: int = Field(default=0, description="Input tokens served from provider cache")
    cache_creation_tokens: int = Field(default=0, description="Input tokens written to provider cache")
    total_tokens: int = Field(default=0, description="Total input and output tokens")
    cache_hit_rate: float | None = Field(default=None, description="Cached input tokens divided by input tokens")
    output_tokens_per_second: float | None = Field(default=None, description="Generation throughput")
    input_cost: float | None = Field(default=None, description="Provider-reported input cost")
    output_cost: float | None = Field(default=None, description="Provider-reported output cost")
    total_cost: float | None = Field(default=None, description="Provider-reported total cost")
    model_call_count: int = Field(default=0, description="Number of model calls in the turn")
    tool_call_count: int = Field(default=0, description="Number of executed tools")
    retry_count: int = Field(default=0, description="Number of retried operations")
    finish_reason: str | None = Field(default=None, description="Provider completion reason")
    error_type: str | None = Field(default=None, description="Failure exception type")
    error_message: str | None = Field(default=None, description="Failure description")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible run metadata")
    tool_calls: list[AgentToolCallOut] = Field(default_factory=list, description="Tool spans in execution order")


class AgentSessionOut(BaseModel):
    """Persisted KCS Agent session with history and aggregate usage."""

    id: str = Field(description="Stable session UUID")
    agent_name: str = Field(description="Agent implementation name")
    title: str | None = Field(default=None, description="Optional user-facing conversation title")
    status: AgentSessionStatus = Field(description="Session lifecycle status")
    created_at: datetime = Field(description="UTC session creation timestamp")
    updated_at: datetime = Field(description="UTC last update timestamp")
    last_activity_at: datetime = Field(description="UTC timestamp of the latest message or run")
    message_count: int = Field(default=0, description="Persisted message count")
    turn_count: int = Field(default=0, description="Completed or attempted agent turn count")
    total_input_tokens: int = Field(default=0, description="Aggregate prompt tokens")
    total_output_tokens: int = Field(default=0, description="Aggregate completion tokens")
    total_reasoning_tokens: int = Field(default=0, description="Aggregate provider-reported reasoning tokens")
    total_cache_read_tokens: int = Field(default=0, description="Aggregate cache-read tokens")
    total_tokens: int = Field(default=0, description="Aggregate token count")
    total_cost: float | None = Field(default=None, description="Aggregate known provider cost")
    average_time_to_first_token_ms: float | None = Field(default=None, description="Mean first-token latency")
    average_output_tokens_per_second: float | None = Field(default=None, description="Mean generation throughput")
    cache_hit_rate: float | None = Field(default=None, description="Aggregate cached-input ratio")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible session metadata")
    messages: list[AgentMessageOut] = Field(default_factory=list, description="Conversation messages in sequence")
    runs: list[AgentRunOut] = Field(default_factory=list, description="Observable agent turns")
    artifacts: list[AgentArtifact] = Field(
        default_factory=list, description="Typed outputs produced by this conversation"
    )
    assets: list[SessionAssetOut] = Field(
        default_factory=list, description="Text, link, image, and file session assets"
    )


class AnalysisMessage(BaseModel):
    """One client-supplied message used to identify the latest conversation turn."""

    role: Literal["user", "assistant"] = Field(description="Conversation participant")
    content: str = Field(min_length=1, description="Plain-text message content")


class AnalyzeRequest(BaseModel):
    """Request for one observable KCS Agent conversation turn."""

    raw_content: str = Field(min_length=1, description="Original unstructured text to organize")
    provider_id: int | None = Field(default=None, description="AI provider configuration selected for this turn")
    reasoning_effort: ReasoningEffort = Field(
        default=ReasoningEffort.OFF,
        description="Requested reasoning intensity; unsupported providers may ignore it",
    )
    messages: list[AnalysisMessage] = Field(
        default_factory=list,
        description="Client conversation snapshot; persisted server history remains authoritative",
    )
    auto_search_similar: bool = Field(default=True, description="Whether to search for similar cards")


class AISettingsIn(BaseModel):
    """AI provider configuration. The API key is encrypted before persistence."""

    provider: str = Field(description="Provider identifier, such as openai or ollama")
    model: str = Field(description="Model identifier used by the provider")
    base_url: str | None = Field(default=None, description="Optional custom endpoint for compatible providers")
    api_key: str | None = Field(default=None, description="Secret key; null or empty keeps the stored key")
    temperature: float = Field(default=0.2, ge=0, le=2, description="Sampling temperature")
    enabled: bool = Field(default=True, description="Whether AI features are enabled")


class AISettingsOut(BaseModel):
    """Legacy singleton AI settings without the encrypted provider secret."""

    id: int = Field(description="Singleton settings record ID")
    provider: str = Field(description="Provider protocol identifier")
    model: str = Field(description="Configured model identifier")
    base_url: str | None = Field(default=None, description="Optional custom endpoint")
    temperature: float = Field(description="Sampling temperature")
    enabled: bool = Field(description="Whether the settings may be used")
    updated_at: datetime = Field(description="UTC last update timestamp")
    api_key_masked: str = Field(description="Configured state without exposing the encrypted API key")


class AIProviderIn(BaseModel):
    """Editable configuration for one AI provider connection."""

    name: str = Field(min_length=1, max_length=100, description="User-defined connection name")
    provider: str = Field(description="Provider protocol identifier")
    model: str = Field(min_length=1, description="Model identifier used by the provider")
    base_url: str | None = Field(default=None, description="Optional custom API base URL")
    api_key: str | None = Field(default=None, description="Secret key; empty keeps the stored key on update")
    temperature: float = Field(default=0.2, ge=0, le=2, description="Sampling temperature")
    enabled: bool = Field(default=True, description="Whether this connection may be selected")


class AIProviderOut(BaseModel):
    """Provider connection metadata without its secret."""

    id: int = Field(description="Local provider configuration ID")
    name: str = Field(description="User-defined connection name")
    provider: str = Field(description="Provider protocol identifier")
    model: str = Field(description="Configured model identifier")
    base_url: str | None = Field(default=None, description="Optional custom API base URL")
    temperature: float = Field(description="Sampling temperature")
    enabled: bool = Field(description="Whether this connection may be selected")
    api_key_configured: bool = Field(description="Whether an encrypted key is stored")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last update timestamp")

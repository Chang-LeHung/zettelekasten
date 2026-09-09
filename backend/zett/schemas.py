from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


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


class SuggestedTag(BaseModel):
    """AI-proposed tag that requires user confirmation before saving."""

    path: str = Field(description="Hierarchical tag path")
    existing: bool = Field(description="Whether the path already exists")
    confidence: float = Field(default=0, ge=0, le=1, description="Model confidence from 0 to 1")
    reason: str | None = Field(default=None, description="Short reason for the recommendation")


class ArtifactType(StrEnum):
    """Kinds of durable outputs that a Zettelkasten Agent session may produce."""

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
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible artifact metadata")


class AgentArtifact(BaseModel):
    """One typed output produced inside a persisted agent conversation."""

    id: str = Field(description="Stable artifact UUID")
    session_id: str = Field(description="Owning agent session UUID")
    artifact_type: ArtifactType = Field(description="Artifact discriminator used for rendering and queries")
    status: ArtifactStatus = Field(description="Current artifact lifecycle state")
    content: ArtifactContent = Field(description="Type-specific editable artifact content")
    raw_content: str | None = Field(default=None, description="Original input associated with this artifact")
    version: int = Field(default=1, ge=1, description="Monotonic revision number")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible artifact metadata")
    created_at: datetime = Field(description="UTC artifact creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


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
    """Complete mutable fields for a persisted Agent conversation."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Optional user-facing conversation title",
    )


class ProviderType(StrEnum):
    """Provider protocols understood by the future model adapter layer."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class ProviderWrite(BaseModel):
    """Complete provider configuration accepted by the storage boundary."""

    name: str = Field(min_length=1, max_length=100, description="User-facing configuration name")
    provider: ProviderType = Field(description="Provider protocol used by the model adapter")
    model: str = Field(min_length=1, max_length=200, description="Provider model identifier")
    base_url: str | None = Field(default=None, description="Optional API endpoint override")
    api_key: str | None = Field(
        default=None,
        min_length=1,
        repr=False,
        exclude=True,
        description="Write-only API key encrypted before persistence",
    )
    enabled: bool = Field(default=True, description="Whether this configuration may be selected")
    metadata: dict[str, object] = Field(default_factory=dict, description="Provider-specific JSON options")


class ProviderOut(BaseModel):
    """Safe provider metadata returned without its API key or ciphertext."""

    id: str = Field(description="Stable provider configuration UUID")
    name: str
    provider: ProviderType
    model: str
    base_url: str | None = None
    api_key_configured: bool = Field(description="Whether an encrypted API key is stored")
    enabled: bool
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProviderConnection(BaseModel):
    """Decrypted configuration consumed transiently by a model adapter."""

    model_config = ConfigDict(frozen=True)

    id: str
    provider: ProviderType
    model: str
    base_url: str | None = None
    api_key: SecretStr | None = Field(default=None, repr=False)
    metadata: dict[str, object] = Field(default_factory=dict)

from datetime import datetime

from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """Input fields used to create or update a hierarchical tag."""

    name: str = Field(min_length=1, max_length=100, description="Display name of the tag")
    parent_id: int | None = Field(default=None, description="Parent tag ID; null creates a root tag")
    description: str | None = Field(default=None, description="Optional explanation of the tag")
    color: str | None = Field(default=None, description="Optional CSS color or hex color")


class TagOut(TagCreate):
    """Serialized tag including its computed path and nested children."""

    id: int = Field(description="Database ID of the tag")
    path: str = Field(description="Full hierarchical path, such as Technology/Python")
    card_count: int = Field(default=0, description="Number of directly linked cards")
    children: list[TagOut] = Field(default_factory=list, description="Direct child tags")


class CardCreate(BaseModel):
    """Input fields used to create or update a knowledge card."""

    type: str = Field(default="note", description="Card type, such as note, idea, quote, or todo")
    title: str = Field(description="Short human-readable card title")
    content: str = Field(description="Normalized card body; Markdown is supported by convention")
    raw_content: str | None = Field(default=None, description="Original unmodified user input")
    summary: str | None = Field(default=None, description="Optional short summary")
    source: str | None = Field(default=None, description="Optional source, URL, book, or person")
    tag_ids: list[int] = Field(default_factory=list, description="IDs of tags linked to this card")


class CardOut(CardCreate):
    """Serialized card including lifecycle metadata and resolved tags."""

    id: str = Field(description="Stable UUID of the card")
    status: str = Field(description="Lifecycle status, currently active")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")
    tags: list[TagOut] = Field(default_factory=list, description="Resolved tag objects")


class AnalyzeRequest(BaseModel):
    """Request for non-destructive AI organization preview."""

    raw_content: str = Field(min_length=1, description="Unstructured text to organize")
    auto_search_similar: bool = Field(default=True, description="Whether to search for similar cards")


class SuggestedTag(BaseModel):
    """AI-proposed tag that requires user confirmation before saving."""

    path: str = Field(description="Hierarchical tag path")
    existing: bool = Field(description="Whether the path already exists")
    confidence: float = Field(default=0, ge=0, le=1, description="Model confidence from 0 to 1")
    reason: str | None = Field(default=None, description="Short reason for the recommendation")


class CardAnalysis(BaseModel):
    """Structured AI result shown in the review screen before persistence."""

    type: str = Field(default="note", description="Suggested card type")
    title: str = Field(description="Suggested card title")
    summary: str = Field(default="", description="Generated summary")
    content: str = Field(description="Normalized card body")
    suggested_tags: list[SuggestedTag] = Field(default_factory=list, description="Suggested tags")
    keywords: list[str] = Field(default_factory=list, description="Extracted keywords")


class AISettingsIn(BaseModel):
    """AI provider configuration. The API key is encrypted before persistence."""

    provider: str = Field(description="Provider identifier, such as openai or ollama")
    model: str = Field(description="Model identifier used by the provider")
    base_url: str | None = Field(default=None, description="Optional custom endpoint for compatible providers")
    api_key: str | None = Field(default=None, description="Secret key; null or empty keeps the stored key")
    temperature: float = Field(default=0.2, ge=0, le=2, description="Sampling temperature")
    enabled: bool = Field(default=True, description="Whether AI features are enabled")

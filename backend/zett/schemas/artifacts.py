"""Write and read models for durable session artifacts."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .cards import CardType, normalize_card_type
from .tags import ArtifactTagOut, SuggestedTag


class ArtifactType(StrEnum):
    """Kinds of durable outputs that a Zettelkasten Agent session may produce."""

    CARD = "card"
    ARTICLE = "article"
    IMAGE = "image"
    SLIDES = "slides"
    LATEX_PDF = "latex_pdf"


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
    title: str = Field(description="Short card title using only the words needed to identify its idea")
    summary: str = Field(default="", description="One brief sentence stating the card's essential meaning")
    card_type: CardType = Field(default=CardType.NOTE, description="Normalized knowledge card category")
    content: str = Field(description="Concise Markdown expressing one idea in the fewest words that preserve meaning")

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


class SlidesArtifactContent(ArtifactContentBase):
    """Editable Markdown source for a concise Reveal.js presentation."""

    artifact_type: Literal[ArtifactType.SLIDES] = ArtifactType.SLIDES
    subtitle: str = Field(default="", description="Optional presentation subtitle")
    content: str = Field(
        description=(
            "Markdown deck: '---' starts a horizontal section and '--' starts a vertical slide within a section; "
            "each slide should fit one viewport"
        )
    )

    @field_validator("content")
    @classmethod
    def validate_pages(cls, value: str) -> str:
        """Require exact two-dimensional separators and non-empty slides."""
        lines = value.splitlines()
        separators = {"---", "--"}
        if any(line.strip() in separators and line not in separators for line in lines):
            raise ValueError("slide separators must be exactly '---' or '--' with no surrounding whitespace")
        separator_indexes = [index for index, line in enumerate(lines) if line in separators]
        if not separator_indexes:
            raise ValueError("slide content must contain at least one line containing only '---' or '--'")
        boundaries = [-1, *separator_indexes, len(lines)]
        pages = [lines[start + 1 : end] for start, end in zip(boundaries[:-1], boundaries[1:], strict=True)]
        if any(not any(line.strip() for line in page) for page in pages):
            raise ValueError("slide content cannot contain an empty page")
        return value


class LatexPdfArtifactCreate(BaseModel):
    """Request a server-managed project directory before writing its source files."""

    model_config = ConfigDict(extra="forbid")
    artifact_type: Literal[ArtifactType.LATEX_PDF] = ArtifactType.LATEX_PDF
    pdf_name: str = Field(min_length=5, max_length=255, description="Compiled PDF basename, including .pdf")

    @field_validator("pdf_name")
    @classmethod
    def validate_pdf_name(cls, value: str) -> str:
        if (
            not value.endswith(".pdf")
            or value in {".pdf", "..pdf"}
            or any(character in "/\\" or ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("pdf_name must be a plain filename ending in .pdf")
        if not value[:-4].strip() or value[:-4] in {".", ".."} or value != value.strip():
            raise ValueError("pdf_name must have a non-empty name without surrounding whitespace")
        return value

    @property
    def title(self) -> str:
        """Derive the searchable title without storing duplicate content metadata."""
        return self.pdf_name[:-4]


class LatexPdfArtifactContent(LatexPdfArtifactCreate):
    """Persisted project reference with a server-assigned directory."""

    project_path: str = Field(
        min_length=1, description="Server-assigned directory for all project source files and the PDF"
    )


ArtifactCreateContent = Annotated[
    CardArtifactContent
    | ArticleArtifactContent
    | ImageArtifactContent
    | SlidesArtifactContent
    | LatexPdfArtifactCreate,
    Field(discriminator="artifact_type"),
]


ArtifactContent = Annotated[
    CardArtifactContent
    | ArticleArtifactContent
    | ImageArtifactContent
    | SlidesArtifactContent
    | LatexPdfArtifactContent,
    Field(discriminator="artifact_type"),
]


class AgentArtifactWrite(BaseModel):
    """Complete write model accepted by the session artifact storage boundary."""

    session_id: str = Field(description="Owning agent session UUID")
    content: ArtifactContent | LatexPdfArtifactCreate = Field(description="Type-specific editable artifact content")
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
    tags: list[ArtifactTagOut] = Field(default_factory=list, description="Confirmed persistent library tags")
    created_at: datetime = Field(description="UTC artifact creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")

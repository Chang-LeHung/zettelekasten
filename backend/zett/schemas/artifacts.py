"""Write and read models for durable session artifacts."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cards import CardType, normalize_card_type
from .tags import ArtifactTagEntity, SuggestedTag


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
    """Editable description and location for an image artifact.

    Exactly one location form is expected:

    - ``source_url``: image stored outside this application.
    - ``asset_path``: relative ObjectKey for a locally stored image.
    """

    artifact_type: Literal[ArtifactType.IMAGE] = ArtifactType.IMAGE
    prompt: str = Field(default="", description="Prompt or creative direction used for the image")
    alt_text: str = Field(default="", description="Accessible description of the image")
    # External URL only. Example: "https://example.com/image.png".
    source_url: str | None = Field(default=None, description="External image URL when the image is remote")
    # Internal ObjectKey only. Example:
    # "assets/sessions/<session_id>/<asset_id>.png". It is not an entity ID
    # and it is never an absolute filesystem path.
    asset_path: str | None = Field(default=None, description="Relative ObjectKey when the image is stored locally")


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
    """Persisted project reference with a server-assigned relative directory key.

    The project directory and compiled PDF are addressed as:

    ``project_path + "/" + pdf_name``

    Example:
        ``project_path = "artifacts/<session_id>/paper"``
        ``pdf_name = "paper.pdf"``
        final key = ``"artifacts/<session_id>/paper/paper.pdf"``
    """

    project_path: str = Field(
        min_length=1,
        description="Server-assigned object key below storage_root for all project files and the PDF",
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
    """Complete write model accepted by the session artifact storage boundary.

    ``content`` is the published artifact and ``draft_content`` is a proposal
    awaiting an explicit user save; a write always states both, because the
    storage replaces the editable fields instead of patching them. At least one
    of the two must be present so every artifact has something to render.
    """

    session_id: str = Field(description="Owning agent session UUID")
    content: ArtifactContent | LatexPdfArtifactCreate | None = Field(
        default=None,
        description="Published artifact content; empty until a user saves",
    )
    draft_content: ArtifactContent | LatexPdfArtifactCreate | None = Field(
        default=None,
        description="Model-proposed content awaiting an explicit user save",
    )
    raw_content: str | None = Field(default=None, description="Original input associated with this artifact")
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT, description="Current artifact lifecycle state")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible artifact metadata")

    @model_validator(mode="after")
    def require_editable_content(self) -> Self:
        """Keep every artifact renderable from its published or draft content."""
        if self.content is None and self.draft_content is None:
            raise ValueError("An artifact write requires published content, draft content, or both")
        return self

    @property
    def editable_content(self) -> ArtifactContent | LatexPdfArtifactCreate:
        """Return the content that describes this artifact right now."""
        return self.content or self.draft_content  # type: ignore[return-value]


class AgentArtifactEntity(BaseModel):
    """One typed output produced inside a persisted agent conversation.

    ``content`` is what the user published and ``draft_content`` is what the
    model proposed since then; ``editable_content`` picks the draft first. Only a
    user save moves a draft into ``content``.

    ``content_url`` is not a database column. It is computed for artifacts that
    own a file, currently LaTeX PDFs and local image artifacts.
    """

    id: str = Field(description="Stable artifact UUID")
    session_id: str = Field(description="Owning agent session UUID")
    artifact_type: ArtifactType = Field(description="Artifact discriminator used for rendering and queries")
    status: ArtifactStatus = Field(description="Current artifact lifecycle state")
    content: ArtifactContent | None = Field(
        default=None,
        description="Published artifact content; empty until a user saves",
    )
    draft_content: ArtifactContent | None = Field(
        default=None,
        description="Model-proposed content awaiting an explicit user save",
    )
    raw_content: str | None = Field(default=None, description="Original input associated with this artifact")
    version: int = Field(default=1, ge=1, description="Monotonic revision number")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible artifact metadata")
    tags: list[ArtifactTagEntity] = Field(default_factory=list, description="Confirmed persistent library tags")
    # Response-only ObjectStore URL. Example:
    # "/api/files/artifacts/<session_id>/<project>/paper.pdf".
    # Null for card/article/slides and for externally referenced images.
    content_url: str | None = Field(
        default=None,
        description="Unified file endpoint URL when this artifact owns a previewable object",
    )
    created_at: datetime = Field(description="UTC artifact creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")

    @property
    def editable_content(self) -> ArtifactContent | None:
        """Return the content the UI and the model should show for this artifact."""
        return self.content or self.draft_content

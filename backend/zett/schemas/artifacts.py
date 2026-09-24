"""Write and read models for durable session artifacts."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .._compat import Self, StrEnum
from .cards import CardType, normalize_card_type
from .common import ImageUrl, NonBlankName500
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

    title: NonBlankName500 = Field(description="User-facing artifact title")
    summary: str = Field(default="", max_length=20_000, description="Generated summary")
    suggested_tags: list[SuggestedTag] = Field(default_factory=list, max_length=100, description="Suggested tags")
    keywords: list[str] = Field(default_factory=list, max_length=100, description="Extracted keywords")


class CardArtifactContent(ArtifactContentBase):
    """Editable content for a knowledge-card artifact."""

    artifact_type: Literal[ArtifactType.CARD] = ArtifactType.CARD
    title: NonBlankName500 = Field(description="Short card title using only the words needed to identify its idea")
    summary: str = Field(
        default="", max_length=20_000, description="One brief sentence stating the card's essential meaning"
    )
    card_type: CardType = Field(default=CardType.NOTE, description="Normalized knowledge card category")
    content: str = Field(
        max_length=1_000_000,
        description="Concise Markdown expressing one idea in the fewest words that preserve meaning",
    )

    @field_validator("card_type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> CardType:
        return normalize_card_type(value)


class ArticleArtifactContent(ArtifactContentBase):
    """Editable content for a long-form Markdown article."""

    artifact_type: Literal[ArtifactType.ARTICLE] = ArtifactType.ARTICLE
    subtitle: str = Field(default="", max_length=500, description="Optional article subtitle")
    content: str = Field(max_length=1_000_000, description="Long-form article body in Markdown")


class ImageArtifactContent(ArtifactContentBase):
    """Editable description and location for an image artifact.

    Exactly one location form is expected:

    - ``source_url``: image stored outside this application.
    - ``asset_path``: relative ObjectKey for a locally stored image.
    """

    artifact_type: Literal[ArtifactType.IMAGE] = ArtifactType.IMAGE
    prompt: str = Field(default="", max_length=100_000, description="Prompt or creative direction used for the image")
    alt_text: str = Field(default="", max_length=10_000, description="Accessible description of the image")
    # External URL only. Example: "https://example.com/image.png".
    source_url: ImageUrl | None = Field(default=None, description="External or data image URL")
    # Internal ObjectKey only. Example:
    # "assets/sessions/<session_id>/<asset_id>.png". It is not an entity ID
    # and it is never an absolute filesystem path.
    asset_path: str | None = Field(default=None, description="Relative ObjectKey when the image is stored locally")


class SlidesArtifactContent(ArtifactContentBase):
    """Editable Markdown source for a concise Reveal.js presentation."""

    artifact_type: Literal[ArtifactType.SLIDES] = ArtifactType.SLIDES
    subtitle: str = Field(default="", max_length=500, description="Optional presentation subtitle")
    content: str = Field(
        max_length=1_000_000,
        description=(
            "Markdown deck: '---' starts a horizontal section and '--' starts a vertical slide within a section; "
            "each slide should fit one viewport"
        ),
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


class ArtifactTextEdit(BaseModel):
    """One exact-text edit inside an artifact body.

    By default ``old_text`` must appear exactly once in the current body, so
    include the surrounding words that make it unique. Set ``replace_all`` when
    every occurrence should change, such as renaming a term. ``new_text`` may be
    empty to delete the matched text.
    """

    model_config = ConfigDict(extra="forbid")

    old_text: str = Field(min_length=1, max_length=100_000, description="Exact text to find in the current body")
    new_text: str = Field(
        default="",
        max_length=100_000,
        description="Replacement text; an empty value deletes the match",
    )
    replace_all: bool = Field(default=False, description="Whether every exact match should be replaced")


class ArtifactContentPatchBase(BaseModel):
    """Fields one partial draft edit may change on every artifact kind.

    Only supplied fields are applied: an omitted or null field keeps its current
    value, while an empty string or empty list clears the field.
    """

    model_config = ConfigDict(extra="forbid")

    title: NonBlankName500 | None = None
    summary: str | None = Field(default=None, max_length=20_000)
    suggested_tags: list[SuggestedTag] | None = Field(default=None, max_length=100)
    keywords: list[str] | None = Field(default=None, max_length=100)


class ArtifactBodyPatchBase(ArtifactContentPatchBase):
    """Partial edit of an artifact whose content is Markdown body text.

    A body changes one of two ways: ``content`` replaces it completely, while
    ``content_edits`` replaces exact snippets inside it. The second form keeps a
    long article or deck from being sent back in full for a small change.
    """

    content: str | None = Field(default=None, max_length=1_000_000)
    content_edits: list[ArtifactTextEdit] | None = Field(default=None, max_length=100)


class CardArtifactPatch(ArtifactBodyPatchBase):
    """Partial edit of a knowledge card."""

    # Required: the patch selects its field set through the artifact type.
    artifact_type: Literal[ArtifactType.CARD]
    card_type: CardType | None = None

    @field_validator("card_type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> object:
        """Normalize a supplied card type while leaving an omitted field alone."""
        return value if value is None else normalize_card_type(value)


class ArticleArtifactPatch(ArtifactBodyPatchBase):
    """Partial edit of a long-form article."""

    artifact_type: Literal[ArtifactType.ARTICLE]
    subtitle: str | None = Field(default=None, max_length=500)


class SlidesArtifactPatch(ArtifactBodyPatchBase):
    """Partial edit of a slide deck."""

    artifact_type: Literal[ArtifactType.SLIDES]
    subtitle: str | None = Field(default=None, max_length=500)


class ImageArtifactPatch(ArtifactContentPatchBase):
    """Partial edit of an image artifact's description or location."""

    artifact_type: Literal[ArtifactType.IMAGE]
    prompt: str | None = Field(default=None, max_length=100_000)
    alt_text: str | None = Field(default=None, max_length=10_000)
    source_url: ImageUrl | None = None
    asset_path: str | None = None


class LatexPdfArtifactPatch(BaseModel):
    """Partial edit of a LaTeX PDF reference.

    ``project_path`` is server-assigned, so a new ``pdf_name`` must be paired
    with the matching canonical project key.
    """

    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal[ArtifactType.LATEX_PDF]
    pdf_name: str | None = None
    project_path: str | None = None


ArtifactContentPatch = Annotated[
    CardArtifactPatch | ArticleArtifactPatch | ImageArtifactPatch | SlidesArtifactPatch | LatexPdfArtifactPatch,
    Field(discriminator="artifact_type"),
]

_CONTENT_ADAPTER = TypeAdapter(ArtifactContent)


def apply_artifact_patch(content: ArtifactContent, patch: ArtifactContentPatch) -> ArtifactContent:
    """Merge one partial edit into existing artifact content.

    The patch describes an editing step, not the whole document:

    - Fields it does not send keep their current value, so changing a title never
      resends a long body.
    - ``content_edits`` replaces exact body snippets, so fixing one paragraph
      costs a paragraph instead of the whole article.
    - A different ``artifact_type`` cannot merge field by field, because the
      variants share only part of their fields, so such a patch must carry the
      complete content of the new type.

    The merged result is validated through the content models, so a patch can
    never store a deck with broken separators or an unknown card type.
    """
    supplied = {
        name: value
        for name, value in patch.model_dump().items()
        if name not in {"artifact_type", "content_edits"} and value is not None
    }
    # Edits stay as models so each pair keeps its validated shape.
    edits = getattr(patch, "content_edits", None)
    if content.artifact_type != patch.artifact_type:
        if edits is not None:
            raise ValueError("content_edits cannot change the artifact type; send the complete content instead")
        return _CONTENT_ADAPTER.validate_python({"artifact_type": patch.artifact_type, **supplied})
    if edits is not None and "content" in supplied:
        raise ValueError("Send either content or content_edits, not both")

    merged = _CONTENT_ADAPTER.validate_python({**content.model_dump(), **supplied})
    if not edits:
        return merged
    body = getattr(merged, "content", None)
    if body is None:
        raise ValueError(f"{merged.artifact_type} artifacts have no body text to edit")
    for edit in edits:
        matches = body.count(edit.old_text)
        if matches == 0:
            raise ValueError(f"content_edits old_text was not found: {_excerpt(edit.old_text)}")
        if matches > 1 and not edit.replace_all:
            raise ValueError(
                "content_edits old_text is not unique; found "
                f"{matches} matches (set replace_all to change every one): {_excerpt(edit.old_text)}"
            )
        body = body.replace(edit.old_text, edit.new_text, -1 if edit.replace_all else 1)
    return _CONTENT_ADAPTER.validate_python({**merged.model_dump(), "content": body})


def _excerpt(value: str, *, limit: int = 60) -> str:
    """Shorten one matched snippet for an error message."""
    collapsed = " ".join(value.split())
    return repr(f"{collapsed[:limit]}…" if len(collapsed) > limit else collapsed)


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
    raw_content: str | None = Field(
        default=None,
        max_length=1_000_000,
        description="Original input associated with this artifact",
    )
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

"""Build bounded, type-specific artifact previews for model-facing context.

``ArtifactPruner`` prevents artifact search results and workspace context from
carrying complete stored documents into the model context. It preserves
identity and routing metadata while exposing only the small, type-specific
fields needed to decide whether an artifact should be fetched in full.

Methods:
    prune: Project an ordered sequence of artifacts without changing its order.
    prune_one: Dispatch by artifact type and build one bounded preview.

Preview policy:
    card: Return the leading body text with a truncation flag.
    article: Return the leading body text with a truncation flag.
    slides: Return the leading Markdown source with a truncation flag.
    image: Return bounded prompt, alt text, and source URL fields without image bytes.
    latex_pdf: Return the user-facing title and PDF name without its server-managed project path.

Every preview omits ``raw_content`` and metadata. Callers that need the full
document must use the separate artifact read operation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..schemas import (
    AgentArtifact,
    ArticleArtifactContent,
    ArtifactContent,
    ArtifactStatus,
    ArtifactTagOut,
    ArtifactType,
    CardArtifactContent,
    CardType,
    ImageArtifactContent,
    LatexPdfArtifactContent,
    SlidesArtifactContent,
    SuggestedTag,
)


class ArtifactPreviewContentBase(BaseModel):
    """Searchable artifact metadata shared by every query preview."""

    title: str
    summary: str = ""
    suggested_tags: list[SuggestedTag] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class CardArtifactPreviewContent(ArtifactPreviewContentBase):
    """Bounded preview of a knowledge card."""

    artifact_type: Literal[ArtifactType.CARD] = ArtifactType.CARD
    card_type: CardType
    content_preview: str
    content_truncated: bool


class ArticleArtifactPreviewContent(ArtifactPreviewContentBase):
    """Bounded preview of a long-form article."""

    artifact_type: Literal[ArtifactType.ARTICLE] = ArtifactType.ARTICLE
    subtitle: str = ""
    content_preview: str
    content_truncated: bool


class ImageArtifactPreviewContent(ArtifactPreviewContentBase):
    """Bounded image metadata without an encoded image payload."""

    artifact_type: Literal[ArtifactType.IMAGE] = ArtifactType.IMAGE
    prompt_preview: str
    prompt_truncated: bool
    alt_text_preview: str
    alt_text_truncated: bool
    source_url_preview: str | None = None
    source_url_truncated: bool = False
    asset_path: str | None = None


class SlidesArtifactPreviewContent(ArtifactPreviewContentBase):
    """Bounded preview of a Reveal.js Markdown deck."""

    artifact_type: Literal[ArtifactType.SLIDES] = ArtifactType.SLIDES
    subtitle: str = ""
    content_preview: str
    content_truncated: bool


class LatexPdfArtifactPreviewContent(ArtifactPreviewContentBase):
    """PDF identity without exposing its server-managed project path."""

    artifact_type: Literal[ArtifactType.LATEX_PDF] = ArtifactType.LATEX_PDF
    pdf_name: str


ArtifactPreviewContent = Annotated[
    CardArtifactPreviewContent
    | ArticleArtifactPreviewContent
    | ImageArtifactPreviewContent
    | SlidesArtifactPreviewContent
    | LatexPdfArtifactPreviewContent,
    Field(discriminator="artifact_type"),
]


class AgentArtifactPreview(BaseModel):
    """Compact artifact projection returned by the model-facing query tool.

    Both sides of the artifact travel together: ``published_content`` is what the
    user saved and ``draft_content`` is what the model proposes since then. After
    a save the two are equal, so the model can always read the draft as its own
    working copy without losing sight of the published text.
    """

    id: str
    session_id: str
    status: ArtifactStatus
    published_content: ArtifactPreviewContent | None = None
    draft_content: ArtifactPreviewContent | None = None
    version: int = Field(ge=1)
    tags: list[ArtifactTagOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ArtifactPruner:
    """Project full artifacts into bounded, type-specific query previews."""

    def __init__(
        self,
        *,
        card_chars: int = 500,
        article_chars: int = 1_200,
        slides_chars: int = 800,
        image_text_chars: int = 500,
        image_url_chars: int = 1_000,
    ) -> None:
        self.card_chars = self._positive("card_chars", card_chars)
        self.article_chars = self._positive("article_chars", article_chars)
        self.slides_chars = self._positive("slides_chars", slides_chars)
        self.image_text_chars = self._positive("image_text_chars", image_text_chars)
        self.image_url_chars = self._positive("image_url_chars", image_url_chars)

    def prune(self, artifacts: Sequence[AgentArtifact]) -> list[AgentArtifactPreview]:
        """Return bounded previews while preserving source ordering."""
        return [self.prune_one(artifact) for artifact in artifacts]

    def prune_one(self, artifact: AgentArtifact) -> AgentArtifactPreview:
        """Project one artifact with its published content and its draft."""
        return AgentArtifactPreview(
            id=artifact.id,
            session_id=artifact.session_id,
            status=artifact.status,
            published_content=self._project(artifact.content),
            draft_content=self._project(artifact.draft_content),
            version=artifact.version,
            tags=artifact.tags,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )

    def _project(self, content: ArtifactContent | None) -> ArtifactPreviewContent | None:
        """Build one bounded, type-specific preview for either side of the pair."""
        match content:
            case CardArtifactContent() as card:
                preview, truncated = self._clip(card.content, self.card_chars)
                projected = CardArtifactPreviewContent(
                    title=card.title,
                    summary=card.summary,
                    suggested_tags=card.suggested_tags,
                    keywords=card.keywords,
                    card_type=card.card_type,
                    content_preview=preview,
                    content_truncated=truncated,
                )
            case ArticleArtifactContent() as article:
                preview, truncated = self._clip(article.content, self.article_chars)
                projected = ArticleArtifactPreviewContent(
                    title=article.title,
                    summary=article.summary,
                    suggested_tags=article.suggested_tags,
                    keywords=article.keywords,
                    subtitle=article.subtitle,
                    content_preview=preview,
                    content_truncated=truncated,
                )
            case ImageArtifactContent() as image:
                prompt, prompt_truncated = self._clip(image.prompt, self.image_text_chars)
                alt_text, alt_text_truncated = self._clip(image.alt_text, self.image_text_chars)
                source_url, source_url_truncated = self._optional_clip(image.source_url, self.image_url_chars)
                projected = ImageArtifactPreviewContent(
                    title=image.title,
                    summary=image.summary,
                    suggested_tags=image.suggested_tags,
                    keywords=image.keywords,
                    prompt_preview=prompt,
                    prompt_truncated=prompt_truncated,
                    alt_text_preview=alt_text,
                    alt_text_truncated=alt_text_truncated,
                    source_url_preview=source_url,
                    source_url_truncated=source_url_truncated,
                    asset_path=image.asset_path,
                )
            case SlidesArtifactContent() as slides:
                preview, truncated = self._clip(slides.content, self.slides_chars)
                projected = SlidesArtifactPreviewContent(
                    title=slides.title,
                    summary=slides.summary,
                    suggested_tags=slides.suggested_tags,
                    keywords=slides.keywords,
                    subtitle=slides.subtitle,
                    content_preview=preview,
                    content_truncated=truncated,
                )
            case LatexPdfArtifactContent() as pdf:
                projected = LatexPdfArtifactPreviewContent(
                    title=pdf.title,
                    pdf_name=pdf.pdf_name,
                )
            case None:
                return None
            case _:
                raise TypeError(f"Unsupported artifact content: {type(content)!r}")
        return projected

    @staticmethod
    def _clip(value: str, limit: int) -> tuple[str, bool]:
        if len(value) <= limit:
            return value, False
        return value[:limit].rstrip(), True

    @classmethod
    def _optional_clip(cls, value: str | None, limit: int) -> tuple[str | None, bool]:
        if value is None:
            return None, False
        return cls._clip(value, limit)

    @staticmethod
    def _positive(name: str, value: int) -> int:
        if value < 1:
            raise ValueError(f"{name} must be at least 1")
        return value

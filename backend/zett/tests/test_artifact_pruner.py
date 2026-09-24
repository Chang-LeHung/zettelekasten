"""Artifact query projections stay bounded and type-specific."""

from datetime import UTC, datetime

import pytest

from zett.application.artifacts.artifact_pruner import (
    ArticleArtifactPreviewContent,
    ArtifactPruner,
    CardArtifactPreviewContent,
    ImageArtifactPreviewContent,
    LatexPdfArtifactPreviewContent,
)
from zett.schemas import (
    AgentArtifactEntity,
    ArticleArtifactContent,
    ArtifactStatus,
    CardArtifactContent,
    ImageArtifactContent,
    LatexPdfArtifactContent,
)


def _artifact(content, artifact_id: str, draft=None) -> AgentArtifactEntity:
    described = content or draft
    now = datetime.now(UTC)
    return AgentArtifactEntity(
        id=artifact_id,
        session_id="session",
        artifact_type=described.artifact_type,
        status=ArtifactStatus.DRAFT,
        content=content,
        draft_content=draft,
        raw_content="raw input " * 1_000,
        version=1,
        metadata={"internal": "metadata " * 1_000},
        created_at=now,
        updated_at=now,
    )


def test_artifact_pruner_returns_bounded_type_specific_previews() -> None:
    pruner = ArtifactPruner(
        card_chars=10,
        article_chars=12,
        slides_chars=8,
        image_text_chars=6,
        image_url_chars=7,
    )
    artifacts = [
        _artifact(CardArtifactContent(title="Card", content="abcdefghijklm"), "card"),
        _artifact(ArticleArtifactContent(title="Article", content="abcdefghijklm"), "article"),
        _artifact(
            ImageArtifactContent(
                title="Image",
                prompt="prompt-long",
                alt_text="alt-long",
                source_url="data:image/png;base64,abcdefghijklm",
                asset_path="assets/sessions/session/asset.png",
            ),
            "image",
        ),
        _artifact(LatexPdfArtifactContent(pdf_name="paper.pdf", project_path="/private/project"), "latex"),
    ]

    previews = pruner.prune(artifacts)

    card = previews[0].published_content
    assert isinstance(card, CardArtifactPreviewContent)
    assert card.content_preview == "abcdefghij"
    assert card.content_truncated is True

    article = previews[1].published_content
    assert isinstance(article, ArticleArtifactPreviewContent)
    assert article.content_preview == "abcdefghijkl"
    assert article.content_truncated is True

    image = previews[2].published_content
    assert isinstance(image, ImageArtifactPreviewContent)
    assert image.prompt_preview == "prompt"
    assert image.alt_text_preview == "alt-lo"
    assert image.source_url_preview == "data:im"
    assert image.source_url_truncated is True
    assert image.asset_path == "assets/sessions/session/asset.png"

    latex = previews[3].published_content
    assert isinstance(latex, LatexPdfArtifactPreviewContent)
    assert latex.pdf_name == "paper.pdf"
    assert "project_path" not in previews[3].model_dump()

    serialized = previews[0].model_dump()
    assert "artifact_type" not in serialized
    assert serialized["published_content"]["artifact_type"] == "card"
    assert serialized["draft_content"] is None
    assert "raw_content" not in serialized
    assert "metadata" not in serialized


def test_artifact_pruner_rejects_nonpositive_limits() -> None:
    with pytest.raises(ValueError, match="card_chars"):
        ArtifactPruner(card_chars=0)


def test_artifact_preview_returns_published_content_and_draft_together() -> None:
    """The model reads what the user kept and what it currently proposes."""
    published = CardArtifactContent(title="Published card", content="Published body")
    draft = CardArtifactContent(title="Draft card", content="Draft body")
    pruner = ArtifactPruner()

    pending = pruner.prune_one(_artifact(published, "card", draft))
    saved = pruner.prune_one(_artifact(published, "card", published))
    unsaved = pruner.prune_one(_artifact(None, "card", draft))

    assert pending.published_content is not None and pending.published_content.title == "Published card"
    assert pending.draft_content is not None and pending.draft_content.title == "Draft card"
    # After a save the draft mirrors the published content instead of disappearing.
    assert saved.published_content == saved.draft_content
    # A draft-only artifact has no published side yet.
    assert unsaved.published_content is None
    assert unsaved.draft_content is not None and unsaved.draft_content.title == "Draft card"

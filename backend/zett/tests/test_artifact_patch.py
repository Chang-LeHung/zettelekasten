"""Partial artifact edits keep every field the model did not mention."""

import pytest
from pydantic import TypeAdapter, ValidationError

from zett.schemas import (
    ArticleArtifactContent,
    ArtifactContentPatch,
    CardArtifactContent,
    SlidesArtifactContent,
    apply_artifact_patch,
)

PATCH_ADAPTER = TypeAdapter(ArtifactContentPatch)


def card() -> CardArtifactContent:
    return CardArtifactContent(
        title="Original title",
        summary="Original summary",
        content="Original body",
        keywords=["cards"],
        suggested_tags=[],
    )


def test_patch_changes_only_the_supplied_fields() -> None:
    patch = PATCH_ADAPTER.validate_python({"artifact_type": "card", "content": "Rewritten body"})

    updated = apply_artifact_patch(card(), patch)

    assert updated.artifact_type == "card"
    assert updated.content == "Rewritten body"
    assert updated.title == "Original title"
    assert updated.summary == "Original summary"
    assert updated.keywords == ["cards"]


def test_patch_clears_a_field_with_an_empty_value() -> None:
    patch = PATCH_ADAPTER.validate_python({"artifact_type": "card", "summary": "", "keywords": []})

    updated = apply_artifact_patch(card(), patch)

    assert updated.summary == ""
    assert updated.keywords == []
    assert updated.title == "Original title"


def test_null_fields_leave_the_current_value_alone() -> None:
    patch = PATCH_ADAPTER.validate_python({"artifact_type": "card", "title": None, "summary": "New summary"})

    updated = apply_artifact_patch(card(), patch)

    assert updated.title == "Original title"
    assert updated.summary == "New summary"


def test_patch_revalidates_the_merged_content() -> None:
    invalid = PATCH_ADAPTER.validate_python({"artifact_type": "slides", "title": "Deck"})
    slides = SlidesArtifactContent(title="Deck", content="# One\n\n---\n\n# Two")

    # Replacing the body with a single unseparated page still has to pass the
    # slide validator, so the merge validates the result instead of trusting it.
    with pytest.raises(ValidationError, match="at least one line"):
        apply_artifact_patch(slides, PATCH_ADAPTER.validate_python({"artifact_type": "slides", "content": "# One"}))

    assert invalid.artifact_type == "slides"


def test_changing_the_artifact_type_replaces_the_whole_content() -> None:
    patch = PATCH_ADAPTER.validate_python({"artifact_type": "article", "title": "Long form", "content": "Article body"})

    updated = apply_artifact_patch(card(), patch)

    assert isinstance(updated, ArticleArtifactContent)
    assert updated.title == "Long form"
    assert updated.content == "Article body"
    assert updated.summary == ""

    # The variants share only part of their fields, so a type change must carry
    # the required fields of the new type.
    with pytest.raises(ValidationError):
        apply_artifact_patch(card(), PATCH_ADAPTER.validate_python({"artifact_type": "article", "title": "Long form"}))


def test_patch_rejects_fields_the_artifact_type_does_not_have() -> None:
    with pytest.raises(ValidationError):
        PATCH_ADAPTER.validate_python({"artifact_type": "card", "subtitle": "Cards have no subtitle"})


def test_content_edits_replace_exact_body_snippets() -> None:
    """One paragraph is cheaper to change than the whole body."""
    article = ArticleArtifactContent(
        title="History",
        content="# History\n\nABC was a language.\n\nIt inspired Python.",
    )
    patch = PATCH_ADAPTER.validate_python(
        {
            "artifact_type": "article",
            "content_edits": [
                {"old_text": "ABC was a language.", "new_text": "ABC was an early teaching language."},
                {"old_text": "It inspired Python.", "new_text": ""},
            ],
        }
    )

    updated = apply_artifact_patch(article, patch)

    assert updated.content == "# History\n\nABC was an early teaching language.\n\n"
    assert updated.title == "History"


def test_content_edits_must_match_exactly_once() -> None:
    article = ArticleArtifactContent(title="History", content="Same line.\n\nSame line.\n")

    with pytest.raises(ValueError, match="was not found"):
        apply_artifact_patch(
            article,
            PATCH_ADAPTER.validate_python(
                {"artifact_type": "article", "content_edits": [{"old_text": "Missing", "new_text": "x"}]}
            ),
        )
    with pytest.raises(ValueError, match="not unique; found 2 matches"):
        apply_artifact_patch(
            article,
            PATCH_ADAPTER.validate_python(
                {"artifact_type": "article", "content_edits": [{"old_text": "Same line.", "new_text": "x"}]}
            ),
        )


def test_content_edits_can_replace_every_occurrence() -> None:
    article = ArticleArtifactContent(
        title="Agent",
        content="Zett keeps drafts.\n\nZett also keeps tags.\n",
    )

    updated = apply_artifact_patch(
        article,
        PATCH_ADAPTER.validate_python(
            {
                "artifact_type": "article",
                "content_edits": [
                    {"old_text": "Zett", "new_text": "Zett Agent", "replace_all": True},
                ],
            }
        ),
    )

    assert updated.content == "Zett Agent keeps drafts.\n\nZett Agent also keeps tags.\n"
    # replace_all still requires the text to exist at all.
    with pytest.raises(ValueError, match="was not found"):
        apply_artifact_patch(
            article,
            PATCH_ADAPTER.validate_python(
                {
                    "artifact_type": "article",
                    "content_edits": [{"old_text": "Missing", "new_text": "x", "replace_all": True}],
                }
            ),
        )


def test_content_edits_revalidate_the_edited_body() -> None:
    slides = SlidesArtifactContent(title="Deck", content="# One\n\n---\n\n# Two")

    with pytest.raises(ValidationError, match="at least one line"):
        apply_artifact_patch(
            slides,
            PATCH_ADAPTER.validate_python(
                {"artifact_type": "slides", "content_edits": [{"old_text": "---", "new_text": ""}]}
            ),
        )


def test_content_and_content_edits_cannot_be_combined_or_retype() -> None:
    article = ArticleArtifactContent(title="History", content="Body")

    with pytest.raises(ValueError, match="Send either content or content_edits"):
        apply_artifact_patch(
            article,
            PATCH_ADAPTER.validate_python(
                {
                    "artifact_type": "article",
                    "content": "Replacement",
                    "content_edits": [{"old_text": "Body", "new_text": "x"}],
                }
            ),
        )
    with pytest.raises(ValueError, match="cannot change the artifact type"):
        apply_artifact_patch(
            article,
            PATCH_ADAPTER.validate_python(
                {
                    "artifact_type": "card",
                    "content": "Card body",
                    "content_edits": [{"old_text": "Body", "new_text": "x"}],
                }
            ),
        )

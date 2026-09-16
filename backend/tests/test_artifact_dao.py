import pytest
from sqlalchemy import select

from zett.infra import database
from zett.infra.dao.artifact import artifact_storage
from zett.infra.dao.session import session_storage
from zett.infra.models import SessionArtifactModel
from zett.infra.storage import Storage
from zett.models import ArtifactListOptions
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArticleArtifactContent,
    ArtifactStatus,
    CardArtifactContent,
    ImageArtifactContent,
    SlidesArtifactContent,
)


async def test_artifact_storage_persists_multiple_typed_outputs_per_session() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    card = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="Small idea", content="A concise note.", card_type="idea"),
        )
    )
    article = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ArticleArtifactContent(title="Long article", subtitle="A subtitle", content="# Body"),
        )
    )
    image = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ImageArtifactContent(title="Architecture", prompt="A clean architecture diagram"),
        )
    )
    slides = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=SlidesArtifactContent(
                title="Architecture review",
                subtitle="A concise walkthrough",
                content="# Context\n\nOne idea per slide.\n\n---\n\n## Decision\n\n- Keep it typed",
            ),
        )
    )

    assert isinstance(artifact_storage, Storage)
    assert [item.id for item in artifact_storage.list(ArtifactListOptions(session_id=session_id))] == [
        card.id,
        article.id,
        image.id,
        slides.id,
    ]
    assert article.content.artifact_type == "article"
    assert image.content.artifact_type == "image"
    assert slides.content.artifact_type == "slides"
    with database.session_scope() as db:
        assert db.scalars(
            select(SessionArtifactModel.artifact_type).order_by(SessionArtifactModel.created_at)
        ).all() == [
            1,
            2,
            3,
            4,
        ]


async def test_artifact_updates_are_versioned_and_cannot_cross_sessions() -> None:
    first_session = (await session_storage.create(AgentSessionCreate())).session_id
    second_session = (await session_storage.create(AgentSessionCreate())).session_id
    created = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=first_session,
            content=ArticleArtifactContent(title="Draft", content="First version"),
        )
    )
    updated = artifact_storage.update(
        created.id,
        AgentArtifactWrite(
            session_id=first_session,
            content=ArticleArtifactContent(title="Revised", content="Second version"),
            status=ArtifactStatus.SAVED,
        ),
    )

    assert updated.version == 2
    assert updated.status == ArtifactStatus.SAVED
    assert updated.content.title == "Revised"

    with pytest.raises(KeyError):
        artifact_storage.update(
            created.id,
            AgentArtifactWrite(
                session_id=second_session,
                content=ArticleArtifactContent(title="Wrong owner", content="Rejected"),
            ),
        )


async def test_artifact_filters_and_explicit_session_cleanup() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    await artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=CardArtifactContent(title="Python", content="Code"))
    )
    await artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=ArticleArtifactContent(title="Python guide", content="Long"))
    )
    await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=SlidesArtifactContent(title="Python slides", content="# Python\n\n---\n\n## Types"),
        )
    )

    articles = artifact_storage.list(
        ArtifactListOptions(session_id=session_id, artifact_types=("article",), query="guide")
    )
    assert [item.content.title for item in articles] == ["Python guide"]
    slides = artifact_storage.list(
        ArtifactListOptions(session_id=session_id, artifact_types=("slides",), query="Python")
    )
    assert [item.content.title for item in slides] == ["Python slides"]
    assert artifact_storage.delete_session(session_id) == 3
    assert artifact_storage.list(ArtifactListOptions(session_id=session_id)) == []


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("# Only one page", "at least one line"),
        ("# First\n --- \n# Second", "exactly '---'"),
        ("# First\n---\n\n---\n# Third", "empty page"),
        ("---\n# Second", "empty page"),
        ("# First\n---", "empty page"),
    ],
)
def test_slides_require_strict_non_empty_page_boundaries(content: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        SlidesArtifactContent(title="Invalid deck", content=content)


def test_slides_support_horizontal_sections_with_vertical_pages() -> None:
    content = "# Section one\n--\n## Detail\n---\n# Section two"

    slides = SlidesArtifactContent(title="Two-dimensional deck", content=content)

    assert slides.content == content


@pytest.mark.parametrize("content", ["# First\n -- \n# Second", "# First\n--\n---\n# Third"])
def test_slides_reject_ambiguous_or_empty_vertical_pages(content: str) -> None:
    with pytest.raises(ValueError):
        SlidesArtifactContent(title="Invalid vertical deck", content=content)

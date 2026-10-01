import pytest
from sqlalchemy import select

from zett.application.tags.tagging import tag_service
from zett.infra.persistence import database
from zett.infra.persistence.dao.artifact import artifact_storage
from zett.infra.persistence.dao.asset import session_asset_storage
from zett.infra.persistence.dao.session import session_storage
from zett.infra.persistence.dao.static_asset import static_asset_storage
from zett.infra.persistence.storage import AsyncStorage
from zett.infra.persistence.tables import SessionArtifactRow
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArticleArtifactContent,
    ArtifactListOptions,
    ArtifactStatus,
    CardArtifactContent,
    ImageArtifactContent,
    SessionAssetCreate,
    SessionAssetType,
    SlidesArtifactContent,
    StaticAssetCreate,
    TagTargetType,
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
    card = await artifact_storage.update(
        card.id,
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="Updated idea", content="A revised note.", card_type="idea"),
        ),
    )

    assert isinstance(artifact_storage, AsyncStorage)
    assert [item.id for item in await artifact_storage.list(ArtifactListOptions(session_id=session_id))] == [
        card.id,
        slides.id,
        image.id,
        article.id,
    ]
    assert article.content.artifact_type == "article"
    assert image.content.artifact_type == "image"
    assert slides.content.artifact_type == "slides"
    async with database.session_scope() as db:
        rows = await db.scalars(select(SessionArtifactRow.artifact_type).order_by(SessionArtifactRow.created_at))
        assert rows.all() == [
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
    updated = await artifact_storage.update(
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
        await artifact_storage.update(
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

    articles = await artifact_storage.list(
        ArtifactListOptions(session_id=session_id, artifact_types=("article",), query="guide")
    )
    assert [item.content.title for item in articles] == ["Python guide"]
    slides = await artifact_storage.list(
        ArtifactListOptions(session_id=session_id, artifact_types=("slides",), query="Python")
    )
    assert [item.content.title for item in slides] == ["Python slides"]
    assert await artifact_storage.delete_session(session_id) == 3
    assert await artifact_storage.list(ArtifactListOptions(session_id=session_id)) == []


async def test_artifact_count_matches_the_filters_it_numbers() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    tagged = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="Python card", content="A short note about Python."),
            # Only a saved artifact can carry a tag, and only saved content is
            # what an external `published_only` search may reveal.
            status=ArtifactStatus.SAVED,
        )
    )
    await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ArticleArtifactContent(title="Python guide", content="A long read about Python."),
        )
    )
    await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=SlidesArtifactContent(title="Rust ownership", content="# Rust\n\n---\n\n## Borrowing"),
        )
    )
    tag = await tag_service.create_path("Python", TagTargetType.ARTIFACT)
    await tag_service.replace_artifact_tags(tagged.id, ["Python"])

    assert await artifact_storage.count(ArtifactListOptions(query="Python")) == 2
    assert await artifact_storage.count(ArtifactListOptions(artifact_types=("slides",))) == 1
    assert await artifact_storage.count(ArtifactListOptions(tag_ids=(tag.id,))) == 1
    assert await artifact_storage.count(ArtifactListOptions(tag_ids=("missing-tag",))) == 0
    # A count answers for the whole filter, never for the page it is sent with.
    assert await artifact_storage.count(ArtifactListOptions(session_id=session_id, limit=1, offset=2)) == 3

    for options in (
        ArtifactListOptions(),
        ArtifactListOptions(session_id=session_id),
        ArtifactListOptions(session_id=session_id, artifact_types=("article",)),
        ArtifactListOptions(session_id=session_id, statuses=("draft",)),
        ArtifactListOptions(session_id=session_id, query="Python"),
        ArtifactListOptions(session_id=session_id, query="Python", published_only=True),
        ArtifactListOptions(session_id=session_id, tag_ids=(tag.id,)),
    ):
        assert await artifact_storage.count(options) == len(await artifact_storage.list(options))


async def test_artifact_search_uses_bm25_and_reindexes_updates() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    title_match = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="Needle in title", content="Unrelated body"),
        )
    )
    content_match = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ArticleArtifactContent(title="Other article", content="The needle appears in this body"),
        )
    )

    matches = await artifact_storage.list(ArtifactListOptions(query="needle"))
    assert [item.id for item in matches] == [title_match.id, content_match.id]

    await artifact_storage.update(
        content_match.id,
        AgentArtifactWrite(
            session_id=session_id,
            content=ArticleArtifactContent(title="Other article", content="Replacement content"),
        ),
    )

    assert [item.id for item in await artifact_storage.list(ArtifactListOptions(query="needle"))] == [title_match.id]
    assert [item.id for item in await artifact_storage.list(ArtifactListOptions(query="replacement"))] == [
        content_match.id
    ]


async def test_artifact_search_supports_chinese_substrings() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    created = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="机器学习笔记", content="向量检索与知识库"),
        )
    )

    assert [item.id for item in await artifact_storage.list(ArtifactListOptions(query="机器学习"))] == [created.id]
    assert [item.id for item in await artifact_storage.list(ArtifactListOptions(query="向量"))] == [created.id]


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


async def _session_image(session_id: str, name: str = "chart.png") -> str:
    """Store one session-owned image and return its ObjectKey."""
    asset = await session_asset_storage.create(
        SessionAssetCreate(
            session_id=session_id,
            asset_type=SessionAssetType.IMAGE,
            name=name,
            mime_type="image/png",
            content=b"\x89PNG\r\n\x1a\n",
        )
    )
    assert asset.storage_path is not None
    return asset.storage_path


async def test_image_artifact_accepts_a_file_this_session_uploaded() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    stored_path = await _session_image(session_id)

    artifact = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED,
            content=ImageArtifactContent(title="Chart", asset_path=stored_path),
        )
    )

    assert artifact.content_url == f"/api/files/{stored_path}"


async def test_image_artifact_refuses_a_path_it_does_not_own_or_cannot_find() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    other_session = (await session_storage.create(AgentSessionCreate())).session_id
    foreign = await _session_image(other_session, "other.png")
    static_asset = await static_asset_storage.create(
        StaticAssetCreate(name="library.png", mime_type="image/png", content=b"\x89PNG\r\n\x1a\n")
    )

    for path, message in (
        (foreign, "this conversation"),
        (static_asset.storage_path, "this conversation"),
        (f"assets/sessions/{session_id}/missing.png", "does not exist"),
        ("../escape.png", "relative object key"),
        ("/tmp/absolute.png", "relative object key"),
    ):
        with pytest.raises(ValueError, match=message):
            await artifact_storage.create(
                AgentArtifactWrite(
                    session_id=session_id,
                    status=ArtifactStatus.SAVED,
                    content=ImageArtifactContent(title="Broken", asset_path=path),
                )
            )

    # An external image needs no local file, and an update cannot slip past the
    # same check by replacing the path of an artifact that already exists.
    await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED,
            content=ImageArtifactContent(title="External", source_url="https://example.com/picture.png"),
        )
    )
    stored_path = await _session_image(session_id, "kept.png")
    stored = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            status=ArtifactStatus.SAVED,
            content=ImageArtifactContent(title="Kept", asset_path=stored_path),
        )
    )

    with pytest.raises(ValueError, match="does not exist"):
        await artifact_storage.update(
            stored.id,
            AgentArtifactWrite(
                session_id=session_id,
                status=ArtifactStatus.SAVED,
                content=ImageArtifactContent(title="Kept", asset_path=f"assets/sessions/{session_id}/gone.png"),
            ),
        )

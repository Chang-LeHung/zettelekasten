from kcs.agent.tools import ArtifactTools
from kcs.application.services import KnowledgeLibraryApplicationService
from kcs.infra.agent_session_dao import agent_session_storage
from kcs.infra.article_dao import ArticleStorage, article_storage
from kcs.infra.storage import Storage
from kcs.models import ArticleListOptions, LibraryListOptions
from kcs.schemas import (
    AgentSessionCreate,
    ArticleArtifactContent,
    ArticleCreate,
    ArtifactStatus,
    CardCreate,
    LibraryItemType,
    LibraryItemUpdate,
)


def test_article_storage_implements_typed_crud_and_search() -> None:
    created = article_storage.create(
        ArticleCreate(
            title="Context compaction",
            subtitle="Snapshots and replay tails",
            summary="Keep durable state while bounding context.",
            content="# Context\n\nCompact older messages.",
            tag_paths=["AI/Agents"],
        )
    )

    assert isinstance(article_storage, Storage)
    assert isinstance(article_storage, ArticleStorage)
    persisted = article_storage.get(created.id)
    assert persisted is not None
    assert persisted.model_dump(exclude={"created_at", "updated_at"}) == created.model_dump(
        exclude={"created_at", "updated_at"}
    )
    assert [article.id for article in article_storage.list(ArticleListOptions(query="replay"))] == [created.id]

    updated = article_storage.update(
        created.id,
        ArticleCreate(title="Context management", content="A revised article."),
    )
    assert updated.title == "Context management"
    assert article_storage.delete(created.id) is True
    assert article_storage.get(created.id) is None


def test_saving_article_publishes_it_into_unified_library() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    tools = ArtifactTools(session.id, raw_content="Write about context management.")
    artifact = tools.create_article(
        ArticleArtifactContent(
            title="Long-form context management",
            subtitle="A practical design",
            summary="Use raw logs and snapshots.",
            content="# Design\n\nRetain immutable logs and compact snapshots.",
        )
    )

    saved = tools.save(artifact.id)
    library = KnowledgeLibraryApplicationService.list(LibraryListOptions())

    assert saved.status == ArtifactStatus.SAVED
    assert saved.linked_resource_id is not None
    assert [(item.item_type, item.title) for item in library] == [
        (LibraryItemType.ARTICLE, "Long-form context management")
    ]
    assert library[0].subtitle == "A practical design"


def test_library_combines_cards_and_articles_and_deletes_by_resource_type() -> None:
    from kcs.application.services import CardApplicationService

    card = CardApplicationService.create(CardCreate(title="Small note", content="A compact idea."))
    article = article_storage.create(ArticleCreate(title="Long article", content="A detailed explanation."))

    items = KnowledgeLibraryApplicationService.list(LibraryListOptions())

    assert {item.item_type for item in items} == {LibraryItemType.CARD, LibraryItemType.ARTICLE}
    assert KnowledgeLibraryApplicationService.delete(LibraryItemType.ARTICLE, article.id) == {"ok": True}
    assert KnowledgeLibraryApplicationService.delete(LibraryItemType.CARD, card.id) == {"ok": True}
    assert KnowledgeLibraryApplicationService.list(LibraryListOptions()) == []


def test_library_updates_editable_fields_and_preserves_resource_metadata() -> None:
    from kcs.application.services import CardApplicationService

    card = CardApplicationService.create(
        CardCreate(type="idea", title="Initial card", content="Initial body", source="Notebook")
    )
    article = article_storage.create(
        ArticleCreate(
            title="Initial article",
            subtitle="Original subtitle",
            content="Initial article body",
            tag_paths=["Engineering/Agents"],
        )
    )

    updated_card = KnowledgeLibraryApplicationService.update(
        LibraryItemType.CARD,
        card.id,
        LibraryItemUpdate(title="Edited card", summary="A summary", content="# Edited card"),
    )
    updated_article = KnowledgeLibraryApplicationService.update(
        LibraryItemType.ARTICLE,
        article.id,
        LibraryItemUpdate(
            title="Edited article",
            subtitle="Updated subtitle",
            summary="Updated summary",
            content="# Edited article",
        ),
    )

    assert updated_card.card_type == "idea"
    assert updated_card.source == "Notebook"
    assert updated_card.content == "# Edited card"
    assert updated_article.subtitle == "Updated subtitle"
    assert updated_article.tag_paths == ["Engineering/Agents"]
    assert updated_article.content == "# Edited article"

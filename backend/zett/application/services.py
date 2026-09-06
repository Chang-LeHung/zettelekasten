from ..domain.services import (
    ArtifactDomainService,
    ArtifactDraft,
    CardDomainService,
    CardDraft,
    SessionAssetDomainService,
    TagDomainService,
)
from ..infra.article_dao import article_storage
from ..infra.card_dao import card_storage
from ..infra.tag_dao import tag_storage
from ..models import (
    AgentSessionListOptions,
    AIProviderListOptions,
    ArticleListOptions,
    CardListOptions,
    LibraryListOptions,
    SessionAssetListOptions,
    TagListOptions,
)
from ..schemas import (
    AgentArtifact,
    AgentSessionCreate,
    AgentSessionTitleUpdate,
    AIProviderIn,
    AISettingsIn,
    AISettingsOut,
    AnalyzeRequest,
    ArticleCreate,
    ArticleOut,
    ArtifactContent,
    CardCreate,
    LibraryItemOut,
    LibraryItemType,
    LibraryItemUpdate,
    SessionAssetCreate,
    SessionAssetType,
    SessionLinkAssetIn,
    SessionTextAssetIn,
    TagCreate,
)


class CardApplicationService:
    """Coordinates card use cases across the domain and persistence layers."""

    @staticmethod
    def create(payload: CardCreate):
        CardDomainService.validate_draft(CardDraft(payload.type, payload.title, payload.content))
        return card_storage.create(payload)

    @staticmethod
    def update(card_id: str, payload: CardCreate):
        CardDomainService.validate_draft(CardDraft(payload.type, payload.title, payload.content))
        return card_storage.update(card_id, payload)

    @staticmethod
    def get(card_id: str):
        return card_storage.get(card_id)

    @staticmethod
    def search(query: str | None, card_type: str | None, tag_id: int | None):
        return card_storage.list(
            CardListOptions(
                q=query, card_types=(card_type,) if card_type else (), include_tag_ids=(tag_id,) if tag_id else ()
            )
        )

    @staticmethod
    def search_options(options: CardListOptions):
        return card_storage.list(options)

    @staticmethod
    def delete(card_id: str):
        return {"ok": card_storage.delete(card_id)}


class ArticleApplicationService:
    """Coordinate permanent article use cases across domain and persistence layers."""

    @staticmethod
    def create(payload: ArticleCreate) -> ArticleOut:
        ArtifactDomainService.validate(ArtifactDraft("article", payload.title, payload.content))
        return article_storage.create(payload)

    @staticmethod
    def update(article_id: str, payload: ArticleCreate) -> ArticleOut:
        ArtifactDomainService.validate(ArtifactDraft("article", payload.title, payload.content))
        return article_storage.update(article_id, payload)

    @staticmethod
    def get(article_id: str) -> ArticleOut | None:
        return article_storage.get(article_id)

    @staticmethod
    def delete(article_id: str) -> dict[str, bool]:
        return {"ok": article_storage.delete(article_id)}


class KnowledgeLibraryApplicationService:
    """Present permanent cards and articles through one read-oriented library boundary."""

    @staticmethod
    def list(options: LibraryListOptions) -> list[LibraryItemOut]:
        requested_types = set(options.item_types or (LibraryItemType.CARD, LibraryItemType.ARTICLE))
        fetch_limit = min(500, options.limit + options.offset)
        items: list[LibraryItemOut] = []
        if LibraryItemType.CARD in requested_types:
            cards = card_storage.list(CardListOptions(q=options.query, tag_id=options.tag_id, limit=fetch_limit))
            items.extend(
                LibraryItemOut(
                    id=card.id,
                    item_type=LibraryItemType.CARD,
                    title=card.title,
                    summary=card.summary,
                    content=card.content,
                    raw_content=card.raw_content,
                    source=card.source,
                    card_type=card.type,
                    status=card.status,
                    tag_paths=[tag.path for tag in card.tags],
                    created_at=card.created_at,
                    updated_at=card.updated_at,
                )
                for card in cards
            )
        if LibraryItemType.ARTICLE in requested_types and options.tag_id is None:
            articles = article_storage.list(ArticleListOptions(query=options.query, limit=fetch_limit))
            items.extend(
                LibraryItemOut(
                    id=article.id,
                    item_type=LibraryItemType.ARTICLE,
                    title=article.title,
                    subtitle=article.subtitle,
                    summary=article.summary,
                    content=article.content,
                    raw_content=article.raw_content,
                    status=article.status,
                    tag_paths=article.tag_paths,
                    created_at=article.created_at,
                    updated_at=article.updated_at,
                )
                for article in articles
            )
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[options.offset : options.offset + options.limit]

    @staticmethod
    def delete(item_type: LibraryItemType, item_id: str) -> dict[str, bool]:
        if item_type == LibraryItemType.CARD:
            return CardApplicationService.delete(item_id)
        return ArticleApplicationService.delete(item_id)

    @staticmethod
    def update(item_type: LibraryItemType, item_id: str, payload: LibraryItemUpdate) -> LibraryItemOut:
        """Update one permanent resource while preserving type-specific metadata."""
        if item_type == LibraryItemType.CARD:
            card = CardApplicationService.get(item_id)
            if card is None:
                raise KeyError(f"Card not found: {item_id}")
            updated = CardApplicationService.update(
                item_id,
                CardCreate(
                    type=card.type,
                    title=payload.title,
                    content=payload.content,
                    raw_content=card.raw_content,
                    summary=payload.summary,
                    source=card.source,
                    tag_ids=card.tag_ids,
                ),
            )
            return LibraryItemOut(
                id=updated.id,
                item_type=LibraryItemType.CARD,
                title=updated.title,
                summary=updated.summary,
                content=updated.content,
                raw_content=updated.raw_content,
                source=updated.source,
                card_type=updated.type,
                status=updated.status,
                tag_paths=[tag.path for tag in updated.tags],
                created_at=updated.created_at,
                updated_at=updated.updated_at,
            )
        article = ArticleApplicationService.get(item_id)
        if article is None:
            raise KeyError(f"Article not found: {item_id}")
        updated_article = ArticleApplicationService.update(
            item_id,
            ArticleCreate(
                title=payload.title,
                subtitle=payload.subtitle or "",
                summary=payload.summary or "",
                content=payload.content,
                raw_content=article.raw_content,
                tag_paths=article.tag_paths,
            ),
        )
        return LibraryItemOut(
            id=updated_article.id,
            item_type=LibraryItemType.ARTICLE,
            title=updated_article.title,
            subtitle=updated_article.subtitle,
            summary=updated_article.summary,
            content=updated_article.content,
            raw_content=updated_article.raw_content,
            status=updated_article.status,
            tag_paths=updated_article.tag_paths,
            created_at=updated_article.created_at,
            updated_at=updated_article.updated_at,
        )


class TagApplicationService:
    """Coordinates tag creation and tree queries."""

    @staticmethod
    def create(payload: TagCreate):
        normalized = payload.model_copy(update={"name": TagDomainService.validate_name(payload.name)})
        return tag_storage.create(normalized)

    @staticmethod
    def tree():
        return tag_storage.list(TagListOptions())

    @staticmethod
    def paths() -> list[str]:
        return [tag.path for tag in tag_storage.list(TagListOptions(tree=False))]


class KnowledgeWorkspaceApplicationService:
    """Coordinate conversations and their polymorphic output artifacts."""

    @staticmethod
    def start_conversation():
        """Create an empty persisted Zett Agent conversation workspace."""
        from ..infra.agent_session_dao import agent_session_storage

        session = agent_session_storage.create(AgentSessionCreate())
        return {"conversation_id": session.id, "artifacts": [], "assets": []}

    @staticmethod
    def list_sessions(options: AgentSessionListOptions):
        """List persisted Zett Agent sessions with aggregate observability metrics."""
        from ..infra.agent_session_dao import agent_session_storage

        return agent_session_storage.list(options)

    @staticmethod
    def get_session(conversation_id: str):
        """Return a persisted session with messages, runs, tools, and artifacts."""
        from ..infra.agent_session_dao import agent_session_storage
        from ..infra.session_asset_dao import session_asset_storage

        session = agent_session_storage.get(conversation_id)
        if session is None:
            return None
        assets = session_asset_storage.list(SessionAssetListOptions(session_id=conversation_id))
        return session.model_copy(update={"assets": assets})

    @staticmethod
    def update_session_title(conversation_id: str, payload: AgentSessionTitleUpdate):
        """Replace a title explicitly and prevent future automatic title generation."""
        from ..infra.agent_session_dao import agent_session_storage

        session = agent_session_storage.get(conversation_id)
        if session is None:
            return None
        title = payload.title.strip()
        if not title:
            raise ValueError("Session title cannot be empty")
        metadata = {**session.metadata, "title_source": "user", "title_finalized": True}
        return agent_session_storage.update(
            conversation_id,
            AgentSessionCreate(title=title, metadata=metadata),
        )

    @staticmethod
    def delete_session(conversation_id: str):
        """Explicitly delete a session and all records owned by its aggregate."""
        from ..infra.agent_runtime import get_agent_runtime_storage
        from ..infra.agent_session_dao import agent_session_storage
        from ..infra.artifact_dao import artifact_storage
        from ..infra.session_asset_dao import session_asset_storage

        session_asset_storage.delete_session(conversation_id)
        artifact_storage.delete_session(conversation_id)
        get_agent_runtime_storage().delete_session(conversation_id)
        return {"ok": agent_session_storage.delete(conversation_id)}

    @staticmethod
    def list_artifacts(conversation_id: str) -> list[AgentArtifact]:
        """List all typed artifacts associated with one conversation."""
        from ..infra.artifact_dao import artifact_storage
        from ..models import ArtifactListOptions

        return artifact_storage.list(ArtifactListOptions(session_id=conversation_id))

    @staticmethod
    def get_artifact(conversation_id: str, artifact_id: str) -> AgentArtifact | None:
        """Read a specific typed artifact from the conversation."""
        from ..infra.artifact_dao import artifact_storage

        artifact = artifact_storage.get(artifact_id)
        return artifact if artifact and artifact.session_id == conversation_id else None

    @staticmethod
    def update_artifact(conversation_id: str, artifact_id: str, content: ArtifactContent) -> AgentArtifact:
        """Replace type-specific artifact content and increment its version."""
        from ..agent import ArtifactTools

        return ArtifactTools(conversation_id).update(artifact_id, content)

    @staticmethod
    def delete_artifact(conversation_id: str, artifact_id: str) -> dict[str, bool]:
        """Delete an artifact and any permanent card linked to it."""
        from ..agent import ArtifactTools

        return {"ok": ArtifactTools(conversation_id).delete(artifact_id)}

    @staticmethod
    def save_artifact(conversation_id: str, artifact_id: str) -> AgentArtifact:
        """Publish a supported artifact to its permanent library aggregate."""
        from ..agent import ArtifactTools

        return ArtifactTools(conversation_id).save(artifact_id)

    @staticmethod
    def stream_conversation(conversation_id: str, request: AnalyzeRequest):
        """Run one tool-calling turn inside an existing conversation."""
        from ..agent import zett_agent
        from ..infra.agent_session_dao import agent_session_storage

        if not agent_session_storage.exists(conversation_id):
            raise KeyError(f"Agent session not found: {conversation_id}")
        return zett_agent.stream(conversation_id, request)

    @staticmethod
    async def summarize_session_title(conversation_id: str, provider_id: int | None) -> None:
        """Generate a session title after the primary streaming response completes."""
        from ..agent import session_title_agent

        await session_title_agent.summarize(conversation_id, provider_id)

    @staticmethod
    def should_generate_session_title(conversation_id: str) -> bool:
        """Return whether the session is still eligible for its one automatic title attempt."""
        from ..infra.agent_session_dao import agent_session_storage

        session = agent_session_storage.get(conversation_id)
        return bool(
            session
            and not session.title
            and not session.metadata.get("title_finalized")
            and not session.metadata.get("title_generation_attempted")
        )


class SessionAssetApplicationService:
    """Coordinate validation, local file storage, and session-scoped asset access."""

    @staticmethod
    def create_text(conversation_id: str, payload: SessionTextAssetIn):
        from ..infra.session_asset_dao import session_asset_storage

        name = SessionAssetDomainService.validate_name(payload.name)
        return session_asset_storage.create(
            SessionAssetCreate(
                session_id=conversation_id,
                asset_type=SessionAssetType.TEXT,
                name=name,
                mime_type=payload.mime_type,
                text_content=payload.content,
                metadata=payload.metadata,
            )
        )

    @staticmethod
    def create_link(conversation_id: str, payload: SessionLinkAssetIn):
        from ..infra.session_asset_dao import session_asset_storage

        name = SessionAssetDomainService.validate_name(payload.name)
        url = SessionAssetDomainService.validate_link(payload.url)
        return session_asset_storage.create(
            SessionAssetCreate(
                session_id=conversation_id,
                asset_type=SessionAssetType.LINK,
                name=name,
                mime_type="text/uri-list",
                source_url=url,
                metadata=payload.metadata,
            )
        )

    @staticmethod
    def create_binary(conversation_id: str, name: str, mime_type: str, content: bytes):
        from ..config import settings
        from ..infra.session_asset_dao import session_asset_storage

        normalized_name = SessionAssetDomainService.validate_name(name)
        if len(content) > settings.max_asset_size_bytes:
            raise ValueError(f"Asset exceeds the {settings.max_asset_size_bytes}-byte upload limit")
        asset_type = SessionAssetType.IMAGE if mime_type.startswith("image/") else SessionAssetType.FILE
        return session_asset_storage.create(
            SessionAssetCreate(
                session_id=conversation_id,
                asset_type=asset_type,
                name=normalized_name,
                mime_type=mime_type or "application/octet-stream",
                content=content,
            )
        )

    @staticmethod
    def list_assets(conversation_id: str):
        from ..infra.agent_session_dao import agent_session_storage
        from ..infra.session_asset_dao import session_asset_storage

        if not agent_session_storage.exists(conversation_id):
            raise KeyError(f"Agent session not found: {conversation_id}")
        return session_asset_storage.list(SessionAssetListOptions(session_id=conversation_id))

    @staticmethod
    def get_asset(conversation_id: str, asset_id: str):
        from ..infra.session_asset_dao import session_asset_storage

        return session_asset_storage.get_for_session(conversation_id, asset_id)

    @staticmethod
    def get_content(conversation_id: str, asset_id: str):
        from ..infra.session_asset_dao import session_asset_storage

        asset = session_asset_storage.get_for_session(conversation_id, asset_id)
        if asset is None:
            return None, None
        return asset, session_asset_storage.content_path(conversation_id, asset_id)

    @staticmethod
    def delete_asset(conversation_id: str, asset_id: str):
        from ..infra.session_asset_dao import session_asset_storage

        asset = session_asset_storage.get_for_session(conversation_id, asset_id)
        return {"ok": session_asset_storage.delete(asset_id) if asset else False}


class AISettingsApplicationService:
    """Coordinates the legacy singleton AI settings use case."""

    @staticmethod
    def get() -> AISettingsOut | None:
        from ..infra.ai_settings_dao import ai_settings_storage

        return ai_settings_storage.get(1)

    @staticmethod
    def update(payload: AISettingsIn) -> AISettingsOut:
        from ..infra.ai_settings_dao import ai_settings_storage

        return ai_settings_storage.update(1, payload)


class AIProviderApplicationService:
    """Coordinates AI provider CRUD through its persistence boundary."""

    @staticmethod
    def list_providers(options: AIProviderListOptions | None = None):
        from ..infra.provider_dao import ai_provider_storage

        return ai_provider_storage.list(options)

    @staticmethod
    def create_provider(payload: AIProviderIn):
        from ..infra.provider_dao import ai_provider_storage

        return ai_provider_storage.create(payload)

    @staticmethod
    def update_provider(provider_id: int, payload: AIProviderIn):
        from ..infra.provider_dao import ai_provider_storage

        return ai_provider_storage.update(provider_id, payload)

    @staticmethod
    def delete_provider(provider_id: int):
        from ..infra.provider_dao import ai_provider_storage

        return {"ok": ai_provider_storage.delete(provider_id)}

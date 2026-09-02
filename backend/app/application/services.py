from ..domain.services import CardDomainService, CardDraft, TagDomainService
from ..infra.card_dao import card_storage
from ..infra.list_options import CardListOptions, TagListOptions
from ..infra.tag_dao import tag_storage
from ..schemas import AnalyzeRequest, CardCreate, TagCreate


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
                query=query, card_types=(card_type,) if card_type else (), include_tag_ids=(tag_id,) if tag_id else ()
            )
        )

    @staticmethod
    def search_options(options: CardListOptions):
        return card_storage.list(options)

    @staticmethod
    def delete(card_id: str):
        return {"ok": card_storage.delete(card_id)}


class TagApplicationService:
    """Coordinates tag creation and tree queries."""

    @staticmethod
    def create(payload: TagCreate):
        normalized = payload.model_copy(update={"name": TagDomainService.validate_name(payload.name)})
        return tag_storage.create(normalized)

    @staticmethod
    def tree():
        return tag_storage.list(TagListOptions())


class CardOrganizationApplicationService:
    """Runs the non-destructive AI organization workflow."""

    @staticmethod
    async def preview(request: AnalyzeRequest):
        from ..ai import analyze

        return await analyze(request)


class AISettingsApplicationService:
    """Coordinates provider settings without exposing stored secrets."""

    @staticmethod
    def get():
        from ..ai import get_settings

        return get_settings()

    @staticmethod
    def update(payload):
        from ..ai import save_settings

        return save_settings(payload)

from ..cards import get_card, save_card, search_cards
from ..database import db
from ..domain.services import CardDomainService, CardDraft, TagDomainService
from ..schemas import AnalyzeRequest, CardCreate, TagCreate
from ..tags import create_tag, list_tags


class CardApplicationService:
    """Coordinates card use cases across the domain and persistence layers."""

    @staticmethod
    def create(payload: CardCreate):
        CardDomainService.validate_draft(CardDraft(payload.type, payload.title, payload.content))
        return save_card(payload)

    @staticmethod
    def update(card_id: str, payload: CardCreate):
        CardDomainService.validate_draft(CardDraft(payload.type, payload.title, payload.content))
        return save_card(payload, card_id)

    @staticmethod
    def get(card_id: str):
        return get_card(card_id)

    @staticmethod
    def search(query: str | None, card_type: str | None, tag_id: int | None):
        return search_cards(query, card_type, tag_id)

    @staticmethod
    def delete(card_id: str):
        with db() as conn:
            deleted = conn.execute("DELETE FROM cards WHERE id=?", (card_id,)).rowcount
            conn.execute("DELETE FROM cards_fts WHERE card_id=?", (card_id,))
        return {"ok": bool(deleted)}


class TagApplicationService:
    """Coordinates tag creation and tree queries."""

    @staticmethod
    def create(payload: TagCreate):
        normalized = payload.model_copy(update={"name": TagDomainService.validate_name(payload.name)})
        return create_tag(normalized)

    @staticmethod
    def tree():
        return list_tags()


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

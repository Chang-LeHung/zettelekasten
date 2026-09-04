from kcs.application.services import CardApplicationService
from kcs.infra.card_dao import card_storage
from kcs.infra.tag_dao import tag_storage
from kcs.schemas import CardCreate, TagCreate


def test_deleting_card_removes_card_and_explicit_tag_links() -> None:
    tag = tag_storage.create(TagCreate(name="Architecture"))
    card = card_storage.create(
        CardCreate(title="Context snapshots", content="Snapshot plus replay tail.", tag_ids=[tag.id])
    )

    assert CardApplicationService.delete(card.id) == {"ok": True}
    assert card_storage.get(card.id) is None
    assert CardApplicationService.delete(card.id) == {"ok": False}

    remaining_tag = tag_storage.get(tag.id)
    assert remaining_tag is not None
    assert remaining_tag.card_count == 0

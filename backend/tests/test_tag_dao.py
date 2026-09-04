import pytest
from fastapi import HTTPException

from kcs.infra.card_dao import card_storage
from kcs.infra.tag_dao import tag_storage
from kcs.models import TagListOptions
from kcs.schemas import CardCreate, TagCreate


def test_tag_storage_uses_typed_models_for_recursive_queries() -> None:
    root = tag_storage.create(TagCreate(name="Engineering"))
    child = tag_storage.create(TagCreate(name="Python", parent_id=root.id))
    leaf = tag_storage.create(TagCreate(name="Typing", parent_id=child.id))
    card_storage.create(CardCreate(title="Type systems", content="Notes", tag_ids=[leaf.id]))

    loaded = tag_storage.get(leaf.id)
    subtree = tag_storage.list(TagListOptions(ancestor_id=root.id, include_descendants=True, tree=False))

    assert loaded is not None
    assert loaded.path == "Engineering/Python/Typing"
    assert loaded.card_count == 1
    assert [tag.id for tag in subtree] == [root.id, child.id, leaf.id]


def test_deleting_tag_explicitly_cleans_links_and_reparents_children() -> None:
    root = tag_storage.create(TagCreate(name="Engineering"))
    child = tag_storage.create(TagCreate(name="Python", parent_id=root.id))
    card = card_storage.create(CardCreate(title="Python", content="Notes", tag_ids=[root.id]))

    assert tag_storage.delete(root.id) is True
    assert tag_storage.delete(root.id) is False
    assert tag_storage.get(root.id) is None
    reparented = tag_storage.get(child.id)
    assert reparented is not None
    assert reparented.parent_id is None
    assert reparented.path == "Python"
    loaded_card = card_storage.get(card.id)
    assert loaded_card is not None
    assert loaded_card.tag_ids == []


def test_tag_storage_rejects_duplicates_and_cycles() -> None:
    root = tag_storage.create(TagCreate(name="Engineering"))
    child = tag_storage.create(TagCreate(name="Python", parent_id=root.id))

    with pytest.raises(HTTPException, match="already exists"):
        tag_storage.create(TagCreate(name="Python", parent_id=root.id))
    with pytest.raises(HTTPException, match="cannot be moved"):
        tag_storage.update(root.id, TagCreate(name="Engineering", parent_id=child.id))

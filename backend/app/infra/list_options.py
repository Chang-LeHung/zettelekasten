from dataclasses import dataclass
from enum import StrEnum


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class CardSortField(StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    TITLE = "title"


class TagSortField(StrEnum):
    NAME = "name"
    CREATED_AT = "created_at"
    CARD_COUNT = "card_count"


@dataclass(frozen=True, slots=True)
class CardListOptions:
    """Structured persistence query options for card listings."""

    query: str | None = None
    card_types: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    include_tag_ids: tuple[int, ...] = ()
    exclude_tag_ids: tuple[int, ...] = ()
    match_all_tags: bool = False
    include_descendants: bool = True
    source: str | None = None
    created_from: str | None = None
    created_to: str | None = None
    updated_from: str | None = None
    updated_to: str | None = None
    has_summary: bool | None = None
    sort_by: CardSortField = CardSortField.UPDATED_AT
    sort_direction: SortDirection = SortDirection.DESC
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class TagListOptions:
    """Structured persistence query options for tag listings."""

    query: str | None = None
    parent_id: int | None = None
    ancestor_id: int | None = None
    include_descendants: bool = False
    tree: bool = True
    sort_by: TagSortField = TagSortField.NAME
    sort_direction: SortDirection = SortDirection.ASC
    limit: int = 500
    offset: int = 0

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CardListOptions:
    """Query options for card listings."""

    query: str | None = None
    card_type: str | None = None
    tag_id: int | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class TagListOptions:
    """Query options for tag listings."""

    parent_id: int | None = None
    tree: bool = True

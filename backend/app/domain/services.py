from dataclasses import dataclass


class DomainError(ValueError):
    """Raised when a domain invariant is violated."""


@dataclass(frozen=True, slots=True)
class CardDraft:
    card_type: str
    title: str
    content: str


class CardDomainService:
    """Pure business rules for card content."""

    @staticmethod
    def validate_draft(draft: CardDraft) -> None:
        if not draft.title.strip():
            raise DomainError("Card title cannot be empty")
        if not draft.content.strip():
            raise DomainError("Card content cannot be empty")
        if not draft.card_type.strip():
            raise DomainError("Card type cannot be empty")


class TagDomainService:
    """Pure business rules for the recursive tag tree."""

    @staticmethod
    def validate_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise DomainError("Tag name cannot be empty")
        return normalized

    @staticmethod
    def validate_move(tag_id: int, parent_id: int | None, descendants: set[int]) -> None:
        if parent_id == tag_id:
            raise DomainError("A tag cannot be its own parent")
        if parent_id is not None and parent_id in descendants:
            raise DomainError("A tag cannot be moved below one of its descendants")

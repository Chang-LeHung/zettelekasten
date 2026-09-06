from dataclasses import dataclass
from urllib.parse import urlsplit


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


class SessionAssetDomainService:
    """Pure validation rules for resources attached to an agent session."""

    @staticmethod
    def validate_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise DomainError("Asset name cannot be empty")
        return normalized

    @staticmethod
    def validate_link(url: str) -> str:
        normalized = url.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise DomainError("Asset links must use an absolute HTTP or HTTPS URL")
        return normalized


@dataclass(frozen=True, slots=True)
class ArtifactDraft:
    """Framework-independent values required to validate one session artifact."""

    artifact_type: str
    title: str
    body: str
    locator: str | None = None


class ArtifactDomainService:
    """Pure invariants shared by card, article, and image artifacts."""

    @staticmethod
    def validate(draft: ArtifactDraft) -> None:
        if not draft.title.strip():
            raise DomainError("Artifact title cannot be empty")
        if draft.artifact_type in ("card", "article") and not draft.body.strip():
            raise DomainError("Text artifacts must contain Markdown content")
        if draft.artifact_type == "image" and not (draft.body.strip() or (draft.locator or "").strip()):
            raise DomainError("Image artifacts require a prompt, asset ID, or source URL")

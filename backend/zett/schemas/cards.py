"""Card-specific finite domain values."""

from .._compat import StrEnum


class CardType(StrEnum):
    """Supported knowledge card categories."""

    NOTE = "note"
    IDEA = "idea"
    QUOTE = "quote"
    TODO = "todo"
    REFERENCE = "reference"


class CardStatus(StrEnum):
    """Where one card stands in its own life.

    The value belongs to the card, not to its text: moving a card along is not an
    edit of the document, so it never creates a draft or needs a save. Each
    card type draws its values from its own slice (``CARD_STATUSES``); the names
    never overlap, so a bare value says which kind of card it describes.
    """

    # todo
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    DONE = "done"
    CANCELLED = "cancelled"
    # idea
    CAPTURED = "captured"
    EXPLORING = "exploring"
    ADOPTED = "adopted"
    DROPPED = "dropped"
    # reference
    UNREAD = "unread"
    READING = "reading"
    READ = "read"


#: The values each card type carries, in the order its menu lists them. The first
#: one is where a new card starts. A type that is absent (note, quote) has no
#: status at all, so its column stays empty.
CARD_STATUSES: dict[CardType, tuple[CardStatus, ...]] = {
    CardType.TODO: (
        CardStatus.OPEN,
        CardStatus.IN_PROGRESS,
        CardStatus.ON_HOLD,
        CardStatus.DONE,
        CardStatus.CANCELLED,
    ),
    CardType.IDEA: (CardStatus.CAPTURED, CardStatus.EXPLORING, CardStatus.ADOPTED, CardStatus.DROPPED),
    CardType.REFERENCE: (CardStatus.UNREAD, CardStatus.READING, CardStatus.READ),
}


def statuses_for(card_type: CardType) -> tuple[CardStatus, ...]:
    """Return the statuses one card type carries; empty when it carries none."""
    return CARD_STATUSES.get(card_type, ())


def default_status(card_type: CardType) -> CardStatus | None:
    """Return where a new card of this type starts, or ``None`` for a statusless type."""
    allowed = statuses_for(card_type)
    return allowed[0] if allowed else None


def normalize_card_type(value: object) -> CardType:
    """Map common model-generated category names to a supported card type."""
    if isinstance(value, CardType):
        return value
    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "knowledge": CardType.NOTE,
        "article": CardType.NOTE,
        "document": CardType.NOTE,
        "insight": CardType.NOTE,
        "concept": CardType.NOTE,
        "thought": CardType.IDEA,
        "brainstorm": CardType.IDEA,
        "suggestion": CardType.IDEA,
        "task": CardType.TODO,
        "action": CardType.TODO,
        "action_item": CardType.TODO,
        "citation": CardType.QUOTE,
        "excerpt": CardType.QUOTE,
        "link": CardType.REFERENCE,
        "resource": CardType.REFERENCE,
    }
    try:
        return CardType(normalized)
    except ValueError:
        return aliases.get(normalized, CardType.NOTE)

"""Card-specific finite domain values."""

from enum import StrEnum


class CardType(StrEnum):
    """Supported knowledge card categories."""

    NOTE = "note"
    IDEA = "idea"
    QUOTE = "quote"
    TODO = "todo"
    REFERENCE = "reference"


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

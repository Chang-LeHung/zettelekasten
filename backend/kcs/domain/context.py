from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextLogEntry:
    """Minimal framework-independent message data used by compaction policy."""

    sequence: int
    content: str


class ContextCompactionPolicy:
    """Decide when to compact and where the immutable log boundary should move."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate mixed CJK and Latin tokens without requiring a provider tokenizer."""
        cjk = sum(1 for character in text if "\u3400" <= character <= "\u9fff")
        other = max(len(text) - cjk, 0)
        return max(1, cjk + (other + 3) // 4) if text else 0

    @classmethod
    def total_tokens(cls, snapshot_text: str, entries: list[ContextLogEntry]) -> int:
        """Estimate the effective historical context size."""
        return cls.estimate_tokens(snapshot_text) + sum(cls.estimate_tokens(entry.content) for entry in entries)

    @staticmethod
    def compactable_prefix(
        entries: list[ContextLogEntry], recent_messages: int, minimum_messages: int
    ) -> list[ContextLogEntry]:
        """Return an old prefix while preserving a verbatim recent-message tail."""
        if len(entries) < minimum_messages + recent_messages:
            return []
        return entries[:-recent_messages] if recent_messages else entries

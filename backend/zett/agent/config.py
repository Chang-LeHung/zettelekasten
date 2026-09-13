"""Configure and build one isolated Agent for each message request."""

from dataclasses import dataclass

from zett_agent import (
    AgentRunConfig,
    AskUserExtension,
    CodingExtension,
    CompactionExtension,
    SessionPersistenceExtension,
    SQLiteSessionStorage,
    TodoWriteExtension,
    ToolGuidelinesExtension,
)

from .assets import AssetExtension
from .extensions import ZettelkastenExtension
from .zettelkasten import ZettelkastenAgent

SYSTEM_PROMPT = """You are the Zettelkasten Agent, an assistant for developing ideas into durable knowledge.
Use the conversation and attached assets as source material. Create or update artifacts only when useful; ordinary
conversation does not require an artifact. Never save or delete an artifact unless the user explicitly requests it.
Use Markdown for card and article bodies. Ask the user when an important ambiguity cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ZettelkastenAgentConfig:
    """Complete construction settings for one request-scoped Agent."""

    session_id: str
    max_iterations: int = 36

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")

    async def create(self, storage: SQLiteSessionStorage) -> ZettelkastenAgent:
        """Build a fresh Agent whose persistence extension restores the session."""
        return await ZettelkastenAgent.create(
            config=AgentRunConfig(session_id=self.session_id),
            system_prompt=SYSTEM_PROMPT,
            extensions=(
                SessionPersistenceExtension(storage),
                AssetExtension(),
                ZettelkastenExtension(),
                CodingExtension(),
                AskUserExtension(),
                TodoWriteExtension(),
                CompactionExtension(),
                ToolGuidelinesExtension(),
            ),
            max_iterations=self.max_iterations,
        )

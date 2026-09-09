"""Process-level composition for the reusable multi-session Agent."""

from zett_agent import (
    AgentConfig,
    AskUserExtension,
    CodingExtension,
    CompactionExtension,
    SessionPersistenceExtension,
    SQLiteSessionStorage,
    TodoWriteExtension,
    ToolGuidelinesExtension,
    new_uuid7,
)

from ..infra.locks import synchronized
from .extensions import ZettelkastenExtension
from .zettelkasten import ZettelkastenAgent

SYSTEM_PROMPT = """You are the Zettelkasten Agent, an assistant for developing ideas into durable knowledge.
Use the conversation and attached assets as source material. Create or update artifacts only when useful; ordinary
conversation does not require an artifact. Never save or delete an artifact unless the user explicitly requests it.
Use Markdown for card and article bodies. Ask the user when an important ambiguity cannot be resolved safely."""

_agent: ZettelkastenAgent | None = None
_AGENT_LOCK = "zettelkasten-agent-runtime"


@synchronized(_AGENT_LOCK)
def _install_agent(candidate: ZettelkastenAgent) -> ZettelkastenAgent:
    """Install one candidate unless another initializer won the race."""
    global _agent
    if _agent is None:
        _agent = candidate
    return _agent


@synchronized(_AGENT_LOCK)
def _current_agent() -> ZettelkastenAgent | None:
    """Read the singleton while serialized with installation and shutdown."""
    return _agent


async def initialize_zettelkasten_agent(storage: SQLiteSessionStorage) -> ZettelkastenAgent:
    """Build the process-wide Agent once during FastAPI startup."""
    current = _current_agent()
    if current is None:
        candidate = await ZettelkastenAgent.create(
            config=AgentConfig(session_id=new_uuid7()),
            system_prompt=SYSTEM_PROMPT,
            extensions=(
                SessionPersistenceExtension(storage),
                ZettelkastenExtension(),
                CodingExtension(),
                AskUserExtension(),
                TodoWriteExtension(),
                CompactionExtension(),
                ToolGuidelinesExtension(),
            ),
        )
        current = _install_agent(candidate)
    return current


@synchronized(_AGENT_LOCK)
def get_zettelkasten_agent() -> ZettelkastenAgent:
    """Return the initialized process-wide Agent."""
    if _agent is None:
        raise RuntimeError("Zettelkasten Agent is not initialized")
    return _agent


@synchronized(_AGENT_LOCK)
def close_zettelkasten_agent() -> None:
    """Release the process reference so the next startup creates fresh extensions."""
    global _agent
    _agent = None

"""Configure and build one isolated Agent for each message request."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from zett_agent import (
    DEFAULT_MCP_CONFIG_PATH,
    DEFAULT_MCP_SERVER_KEYS,
    AgentRunConfig,
    AskUserExtension,
    CodingExtension,
    CompactionExtension,
    McpExtension,
    McpServer,
    SessionPersistenceExtension,
    SkillExtension,
    SQLiteSessionStorage,
    TodoWriteExtension,
    ToolGuidelinesExtension,
)

from .assets import AssetExtension
from .context_composition import ContextCompositionExtension
from .extensions import ZettelkastenExtension
from .zettelkasten import ZettelkastenAgent

SYSTEM_PROMPT = """You are the Zettelkasten Agent, an assistant for developing ideas into durable knowledge.
Use the conversation and attached assets as source material. Create or update artifacts only when useful; ordinary
conversation does not require an artifact. Never save or delete an artifact unless the user explicitly requests it.
Use Markdown for card, article, and slide bodies. A card captures one idea: make it simple and concise, using the
fewest words that preserve its meaning. Separate slide pages with a line containing exactly '---' and no surrounding
characters or whitespace; never create empty slides. Keep every slide concise enough to fit without overflowing.
Ask the user when an important ambiguity cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ZettelkastenAgentConfig:
    """Complete construction settings for one request-scoped Agent.

    Defaults are explicit: Zett discovers skills only below
    ``~/.zett/skills``, while MCP servers are loaded from
    ``~/.zett/mcp.json`` when that file exists. Explicit servers are merged
    with the configured file. Set ``mcp_config_path`` to ``None`` to disable
    file loading; ``mcp_server_keys`` controls which JSON root names are valid.
    """

    session_id: str
    max_iterations: int = 36
    compaction_max_tokens: int = 128_000
    compaction_keep_recent_tokens: int = 32_000
    context_composition_recorder: Callable[[str, dict[str, float]], Awaitable[None]] | None = None
    skill_roots: tuple[str | Path, ...] = ("~/.zett/skills",)
    mcp_servers: tuple[McpServer, ...] = ()
    mcp_config_path: str | Path | None = DEFAULT_MCP_CONFIG_PATH
    mcp_server_keys: tuple[str, ...] = DEFAULT_MCP_SERVER_KEYS

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")
        if not 128_000 <= self.compaction_max_tokens <= 800_000:
            raise ValueError("compaction_max_tokens must be between 128000 and 800000")
        if not 32_000 <= self.compaction_keep_recent_tokens <= 256_000:
            raise ValueError("compaction_keep_recent_tokens must be between 32000 and 256000")
        if self.compaction_keep_recent_tokens >= self.compaction_max_tokens:
            raise ValueError("compaction_keep_recent_tokens must be below compaction_max_tokens")

    async def create(self, storage: SQLiteSessionStorage) -> ZettelkastenAgent:
        """Build a fresh Agent whose persistence extension restores the session."""
        mcp_config_path = self._resolved_mcp_config_path()
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
                CompactionExtension(
                    max_tokens=self.compaction_max_tokens,
                    keep_recent_tokens=self.compaction_keep_recent_tokens,
                ),
                SkillExtension(self.skill_roots),
                McpExtension(
                    servers=self.mcp_servers,
                    config_path=mcp_config_path,
                    server_keys=self.mcp_server_keys,
                ),
                ToolGuidelinesExtension(),
                ContextCompositionExtension(self.context_composition_recorder),
            ),
            max_iterations=self.max_iterations,
        )

    def _resolved_mcp_config_path(self) -> str | Path | None:
        """Treat the absent default file as optional while keeping custom paths strict."""
        if self.mcp_config_path is None:
            return None
        configured = Path(self.mcp_config_path).expanduser().resolve()
        default = DEFAULT_MCP_CONFIG_PATH.expanduser().resolve()
        if configured == default and not configured.is_file():
            return None
        return self.mcp_config_path

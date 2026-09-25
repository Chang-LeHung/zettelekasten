"""Typed configuration for one Zettelkasten Agent request."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from zett_agent import (
    DEFAULT_MCP_SERVER_KEYS,
    McpServer,
    ModelUsageActivityStorage,
    ShellApprovalStorage,
    SQLiteSessionStorage,
)

from ..config import settings
from .container import ZettelkastenExt
from .plugins import SkillSlashCommandExtension

DEFAULT_ZETT_MCP_CONFIG_PATH = Path("~/.zettelekasten/mcp.json")
DEFAULT_ZETT_SKILL_ROOTS = ("~/.zettelekasten/skills",)

SYSTEM_PROMPT = """You are the Zettelkasten Agent, an assistant for developing ideas into durable knowledge.
Use the conversation and attached assets as source material. Create or update artifacts only when useful; ordinary
conversation does not require an artifact. Creating an artifact stores its initial content directly; later updates
normally stage drafts the user reviews and saves unless a headless run is configured for direct current-session edits.
Never claim an artifact is saved unless the user saves it. Never delete an artifact unless the user explicitly
requests it.
A LaTeX PDF artifact owns a git repository you maintain with the shell: initialize that repository and add a
.gitignore for the LaTeX build output before writing any source file, commit every meaningful change yourself with a
Conventional Commit message, and leave the project committed, because saving the artifact is refused while the
project is not a repository or still has uncommitted changes.
Use Markdown for card, article, and slide bodies. A card captures one idea: make it simple and concise, using the
fewest words that preserve its meaning. In slide decks, use an exact '---' line between horizontal sections and an
exact '--' line between vertically related slides inside one section. Never create empty slides. Keep every slide
concise enough to fit without overflowing. Begin every slide, including vertical detail pages, with its own short
Markdown heading that names the slide's topic.
Start every horizontal section with a standalone title-only page, then use '--' before its content pages.
Ask the user when an important ambiguity cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ZettelkastenAgentConfig:
    """Complete construction settings for one request-scoped Agent.

    Defaults are explicit: Zett discovers skills only below
    ``~/.zettelekasten/skills``, while MCP servers are loaded from
    ``~/.zettelekasten/mcp.json`` when that file exists. Explicit servers are merged
    with the configured file. Set ``mcp_config_path`` to ``None`` to disable
    file loading; ``mcp_server_keys`` controls which JSON root names are valid.
    """

    session_id: str
    max_iterations: int = 128
    max_asset_size_bytes: int = settings.max_asset_size_bytes
    compaction_max_tokens: int = 800_000
    compaction_keep_recent_tokens: int = 64_000
    usage_activity_storage: ModelUsageActivityStorage | None = None
    shell_approval_storage: ShellApprovalStorage | None = None
    storage: SQLiteSessionStorage | None = field(default=None, repr=False, compare=False)
    context_composition_recorder: Callable[[str, dict[str, float]], Awaitable[None]] | None = None
    skill_roots: tuple[str | Path, ...] = DEFAULT_ZETT_SKILL_ROOTS
    extensions: tuple[ZettelkastenExt, ...] | None = None
    mcp_servers: tuple[McpServer, ...] = ()
    mcp_config_path: str | Path | None = DEFAULT_ZETT_MCP_CONFIG_PATH
    mcp_server_keys: tuple[str, ...] = DEFAULT_MCP_SERVER_KEYS
    interactive: bool = True
    coding_enabled: bool = True
    allow_direct_artifact_edits: bool = False

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")
        if isinstance(self.max_asset_size_bytes, bool) or self.max_asset_size_bytes < 1:
            raise ValueError("max_asset_size_bytes must be a positive integer")
        if not 128_000 <= self.compaction_max_tokens <= 800_000:
            raise ValueError("compaction_max_tokens must be between 128000 and 800000")
        if not 32_000 <= self.compaction_keep_recent_tokens <= 256_000:
            raise ValueError("compaction_keep_recent_tokens must be between 32000 and 256000")
        if self.compaction_keep_recent_tokens >= self.compaction_max_tokens:
            raise ValueError("compaction_keep_recent_tokens must be below compaction_max_tokens")

    def resolved_extensions(self) -> tuple[ZettelkastenExt, ...]:
        """Load configured extensions, defaulting to local skill commands."""
        if self.extensions is not None:
            return self.extensions
        return (SkillSlashCommandExtension(self.skill_roots),)

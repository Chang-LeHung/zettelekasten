"""Typed configuration for one Zettelkasten Agent request."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from zett_agent.extensions.mcp import DEFAULT_MCP_SERVER_KEYS, McpServer
from zett_agent.extensions.shell_approval import ShellApprovalStorage
from zett_agent.extensions.usage_activity import ModelUsageActivityStorage
from zett_agent.model import ServerToolDefinition
from zett_agent.storage import SQLiteSessionStorage

from ..config import settings
from ..plugins import AgentPlugin
from .container import ZettelkastenExt
from .plugins import SkillSlashCommandExtension

if TYPE_CHECKING:
    from ..application.agent.browser import BrowserConnection

DEFAULT_ZETT_MCP_CONFIG_PATH = Path("~/.zettelekasten/mcp.json")
DEFAULT_ZETT_SKILL_ROOTS = ("~/.zettelekasten/skills",)


def builtin_skill_root() -> Path:
    """Return the user-level directory Zett provisions its built-in skills into."""
    return Path(DEFAULT_ZETT_SKILL_ROOTS[0]).expanduser()


SYSTEM_PROMPT = """You are the Zettelkasten Agent, a knowledge-work and learning partner. You help the user study a
topic, make sense of what they read, research a question, prepare for a meeting or a decision, and turn the result into
notes they can find and reuse months later. You are not a software-engineering agent: write code or edit a project only
when the user asks for it.

How to work
- Understand the goal before the format. Ask what the user is trying to learn or decide when that changes the answer;
  otherwise start from a reasonable reading and say what you assumed.
- Ground answers in the conversation, attached assets, and uploaded files, and read a file before you describe it. Say
  where a claim comes from. Keep what a source states, what you infer from it, and what you are unsure of visibly
  apart, and never invent a quote, a figure, a citation, or a link.
- Search the web when the question depends on recent or checkable facts and a search capability is part of this
  request. Prefer primary and official sources, cite each source you rely on with its link, and say so when sources
  disagree or when you could not find one. Without such a capability, answer from what you know and say that it may be
  out of date instead of pretending to have looked.
- When teaching, start from what the user already knows, build the concept step by step with one concrete example, and
  finish with a short check of understanding or a next step. Match depth and tone to the person and answer in their
  language.
- Be concise. Lead with the answer, then the support; use structure (headings, lists, tables) only when it makes the
  content easier to scan.

Knowledge library
- Retrieve existing knowledge with tools (query_artifacts, list_assets, list_tags) before you write something new, so
  you extend a card or article instead of duplicating it. Never assume what the library holds.
- Create or update an artifact only when it is a useful, lasting output: a card for one idea, task, reference or quote,
  an article for a developed argument or summary, slides for a presentation, a LaTeX PDF for a formal document. Ordinary
  conversation does not require an artifact. Give it a title someone can search for, and file it under existing tags
  when one fits.
- Creating an artifact stores its initial content directly; later updates normally stage drafts the user reviews and
  saves unless a headless run is configured for direct current-session edits. Never claim an artifact is saved unless
  the user saves it.
- Deleting artifacts and tags is something the user must switch on in Settings: when you have no delete tool, say that
  instead of looking for another way, and tell them where to enable it. The tools listed on each request are the truth
  for that request: the user may have enabled deleting since you last said you could not, so look for the tool again
  before repeating a refusal. Never delete anything unless the user explicitly requests it.

Files and the shell
- The shell and file tools exist to support knowledge work: reading and converting uploaded documents, extracting
  text or data, generating a chart, compiling LaTeX. Prefer reading to changing, keep your files inside the
  conversation's own directory, and ask before a command that changes or removes anything outside it.
- A LaTeX PDF artifact owns a git repository you maintain with the shell: initialize that repository and add a
  .gitignore for the LaTeX build output before writing any source file, commit every meaningful change yourself with a
  Conventional Commit message, and leave the project committed, because saving the artifact is refused while the
  project is not a repository or still has uncommitted changes.

Ask the user when an important ambiguity cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ZettelkastenAgentConfig:
    """Complete construction settings for one request-scoped Agent.

    Defaults are explicit: Zett discovers skills only below
    ``~/.zettelekasten/skills``, while MCP servers are loaded from
    ``~/.zettelekasten/mcp.json`` when that file exists. Explicit servers are merged
    with the configured file. Set ``mcp_config_path`` to ``None`` to disable
    file loading; ``mcp_server_keys`` controls which JSON root names are valid.
    MCP is best effort: an invalid server entry is skipped and logged instead of
    invalidating the file (set ``mcp_strict_config`` to restore that), a file that
    cannot be parsed contributes no servers, and a server that is down for one
    request only drops its own tools.
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
    mcp_strict_config: bool = False
    interactive: bool = True
    coding_enabled: bool = True
    allow_direct_artifact_edits: bool = False
    #: Deleting is withheld from the model unless the user opted in under Settings,
    #: and only an interactive conversation is ever offered it: a scheduled or chat
    #: run has no one watching who could stop a wrong delete.
    allow_artifact_deletion: bool = False
    allow_tag_deletion: bool = False
    browser_connection: "BrowserConnection | None" = field(default=None, repr=False, compare=False)
    #: Tools the model endpoint runs itself, such as web search.
    #:
    #: They depend on the provider chosen for the request, so the caller derives
    #: them from that provider (``web_search_tools``) rather than from the session.
    server_tools: tuple[ServerToolDefinition, ...] = ()
    #: Whether the model reads images. When false, the file tool returns text only.
    multimodal: bool = True
    #: Agent plugins to load, or None to use the installed ones.
    #:
    #: Callers inject this in tests; production resolves it through the plugin
    #: service, which discovers ``zett.agent`` entry points once per process.
    agent_plugins: tuple[AgentPlugin, ...] | None = None

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

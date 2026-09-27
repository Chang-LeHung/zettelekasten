"""The skill Zett hands to an external coding agent, and where each agent reads it.

Zett's own agent is served its skills from the configured skill root at startup
(``builtin.py``). A coding agent that runs outside Zett — Claude Code, Codex, or
anything else that reads Agent Skills — has its own directory instead, so
``zett install`` writes the same kind of ``SKILL.md`` there. The content lives in
code for the reason the built-in skill's does: the CLI it documents ships in this
package, so the two cannot drift, and an edited file is never overwritten without
an explicit ``--force``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..log import get_logger
from .builtin import SKILL_FILE_NAME

logger = get_logger(__name__)

#: Directory name written below one agent's skill root.
CLI_SKILL_NAME = "zett-cli"

CLI_SKILL = """---
name: zett-cli
description: Drive Zett's knowledge library from a shell with the `zett` CLI — create, read, list, and delete library artifacts, and manage the tag taxonomy. Read before creating, classifying, or deleting anything in Zett.
---

# Zett from the command line

Zett is a local-first workspace for notes, artifacts, and scheduled agent runs.
`zett artifact` and `zett tag` talk HTTP to the local server recorded in
`<storage_root>/runtime.json` (`~/.zettelekasten` by default), so the server has
to be running first:

```bash
zett status     # is it up? reads runtime.json and never probes a port
zett start      # serve detached, and return once the recorded port answers
zett stop
```

## Keep the content concise, a card most of all

An artifact is something a person re-reads later, not a record of the work that
produced it. Write the conclusion and leave the process out.

- A card is one idea in the fewest words that preserve it: a short title, a
  one-sentence summary, and a body of a few lines. A second paragraph is usually
  an article, so create the article instead of growing the card.
- Never pad a card to look substantial. No restating the title in the first
  line, no "in this card we will", no closing recap of what was just said.
- An article earns its length one idea per section, and a slide earns one idea
  per page: a deck is read while someone talks, not instead of them.
- Never paste a whole file, diff, log, or conversation into a body. Name the
  conclusion and keep the evidence in a few lines that carry it.
- Keep `--summary` to one sentence. A summary that repeats the body end to end
  is a second copy of it.
- Write the artifact itself, never a report about it: no "I created", no tool
  narration, no "as requested".

## Artifacts that belong to no conversation

`zett artifact` creates and reads library artifacts: artifacts that belong to no
conversation. The server keeps one hidden library session for them, so the
library view lists them like any other artifact and the conversation sidebar
never grows a chat for them. Such an artifact has no conversation to attribute it
to, so `--source` is required and names who created it.

```bash
zett artifact create --type card --title "Idea" --body "One sentence." --source claude
cat notes.md | zett artifact create --type article --title "Notes" --body-file - --source codex
zett artifact create --type slides --title "Deck" --body "# One\\n---\\n# Two" --source claude
zett artifact list --query notes
zett artifact list --limit 50
zett artifact get <artifact-id>
zett artifact delete <artifact-id>
```

Rules that matter:

- `--type` is card, article, or slides. An image artifact needs an uploaded asset
  and a LaTeX PDF needs a server-managed project directory, so the CLI creates
  neither one.
- `--body-file -` reads the body from standard input, which keeps a long document
  out of the argument list.
- `--status` defaults to `saved`, which is what makes an artifact appear in the
  library; `--status draft` stores it without publishing it there.
- `--metadata KEY=VALUE` repeats for extra fields; `source` comes from
  `--source` and cannot be repeated here.
- `delete` only removes an artifact that belongs to no conversation: one a
  conversation owns answers 403 and stays, and its conversation deletes it.

## Tags

Tags are one shared library taxonomy: paths are normalized, missing parent nodes
are created as you go, and only saved artifacts carry assignments.

```bash
zett tag list                                      # path  direct/total  id
zett tag list --json
zett tag create Engineering/Python --description "Python notes" --color "#3b82f6"
zett tag update <tag-id> --path Engineering/Async --color "#8fa397"
zett tag delete <tag-id> --recursive --force

zett tag add <artifact-id> Engineering/Python       # keeps the tags it already has
zett tag remove <artifact-id> Engineering/Python    # detach one existing tag
zett tag set <artifact-id> Projects/Zett Release    # replace the whole set
zett tag set <artifact-id> --clear                  # remove every tag
```

Rules that matter:

- Run `zett tag list` before creating anything and reuse an existing path that
  already means the same thing.
- `direct` counts artifacts tagged exactly there, `total` adds its descendants,
  so a parent reads `0/1` when the only assignment sits on its child.
- `add` and `remove` name paths and change exactly that one assignment; `set` is
  the whole-set replace. Only `set` removes a tag you did not name, so reach for
  `add` when you mean "also".
- `delete` refuses while the tag has children or assignments unless you pass
  `--recursive` and `--force`, because those remove other people's work.
- A tag an agent suggests inside a conversation is a proposal: it becomes an
  assignment when the user saves the artifact.

## What the command line checks for you

A blank title, a control character, a body over a megabyte, and an unknown
metadata key are usage errors (`exit 2`) instead of a stored mess, and a request
the server refuses (403, 404, 422) exits `1` with the server's message. Read the
message: it names the limit that was crossed, so the fix is usually the value
itself rather than a retry.
"""


@dataclass(frozen=True, slots=True)
class CodingAgent:
    """One coding agent that reads Agent Skills, and the root it reads them from."""

    #: Value a user passes to ``zett install``.
    name: str
    #: How the agent is named in output.
    label: str
    #: Directory below which the agent looks for ``<skill>/SKILL.md``.
    skill_root: Path


#: Agents ``zett install`` knows by name, in listing order. Every entry names a
#: directory its owner documents, so an install writes where the agent actually
#: reads; anything else is served by ``--dir`` instead of a guess.
CODING_AGENTS: tuple[CodingAgent, ...] = (
    CodingAgent(name="claude", label="Claude Code", skill_root=Path("~/.claude/skills")),
    CodingAgent(name="codex", label="Codex", skill_root=Path("~/.codex/skills")),
)


@dataclass(frozen=True, slots=True)
class SkillInstall:
    """What one install did, so the command can print it and a test can assert it."""

    agent: str | None
    root: Path
    path: Path
    #: ``installed`` wrote a new file, ``updated`` replaced one that differed,
    #: and ``unchanged`` found the shipped content already there.
    state: str


class SkillRefusedError(RuntimeError):
    """Raised when a skill file exists with content the caller did not confirm replacing."""


def find_agent(name: str) -> CodingAgent | None:
    """Return the agent registered under ``name``, or ``None``."""
    return next((agent for agent in CODING_AGENTS if agent.name == name), None)


def install_skill(root: Path, *, agent: str | None = None, force: bool = False) -> SkillInstall:
    """Write the Zett skill below one skill root.

    The file is written only when it is missing or ``force`` confirms replacing
    content that differs from what this package ships. Identical content is left
    alone, so running the command twice never touches the file's timestamp.
    """
    resolved = root.expanduser()
    if resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError(f"{resolved} is not a directory")
    path = resolved / CLI_SKILL_NAME / SKILL_FILE_NAME
    state = "installed"
    if path.is_file():
        if path.read_text(encoding="utf-8") == CLI_SKILL:
            return SkillInstall(agent=agent, root=resolved, path=path, state="unchanged")
        if not force:
            raise SkillRefusedError(f"{path} already exists and differs from the shipped skill")
        state = "updated"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CLI_SKILL, encoding="utf-8")
    logger.info("Installed the Zett skill; agent=%s path=%s state=%s", agent or "custom", path, state)
    return SkillInstall(agent=agent, root=resolved, path=path, state=state)

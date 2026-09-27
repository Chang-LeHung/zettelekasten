"""Install Zett's CLI skill into a coding agent that runs outside Zett.

A coding agent reads Agent Skills from its own directory, so helping Claude Code,
Codex, or another harness use the `zett` CLI means writing one `SKILL.md` where
that agent looks for it. This command only writes files: it never talks to the
server, so it works whether or not Zett is running, and it refuses to replace a
skill the agent's owner may have edited unless --force confirms it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from . import PROGRAM_NAME, validation
from .errors import UsageError, run

if TYPE_CHECKING:
    from ..infra.skills.coding_agents import CodingAgent

#: Longest skill root a user may name. A longer path is a typo, not a directory.
MAX_ROOT_CHARS = 4096

#: How each install state reads in one line of output.
STATE_LABELS = {
    "installed": "Installed the Zett skill",
    "updated": "Updated the Zett skill",
    "unchanged": "The Zett skill is already installed",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for ``zett install``."""
    parser = argparse.ArgumentParser(
        prog=f"{PROGRAM_NAME} install",
        description=(
            "Install Zett's skill into a coding agent, so it can create library artifacts and manage "
            "tags with the `zett` CLI. The skill is written below the agent's own skill root; an "
            "existing file that differs from the shipped one is kept until --force confirms replacing it."
        ),
        epilog=(
            "Name an agent to install into it, or pass --dir for a harness this command does not know. "
            "`zett install --list` prints every known agent and the directory it reads."
        ),
    )
    parser.add_argument(
        "agent",
        nargs="?",
        help="Agent to install into, as `zett install --list` names it",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_agents",
        help="List the supported agents and the skill root each one reads",
    )
    parser.add_argument(
        "--dir",
        dest="directory",
        metavar="PATH",
        help="Install into this skill root instead of a named agent's",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace a skill file whose content differs from the shipped one",
    )
    parser.add_argument("--json", action="store_true", help="Print the installed path and state as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Install the skill and return the exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(parser, lambda namespace: _install(namespace, parser), args)


def _install(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Resolve the target skill root, install into it, and report what happened."""
    from ..infra.skills.coding_agents import (
        CODING_AGENTS,
        SkillRefusedError,
        find_agent,
        install_skill,
    )

    if args.list_agents:
        if args.agent is not None or args.directory is not None:
            raise UsageError("--list cannot be combined with an agent or --dir")
        _print_agents(CODING_AGENTS)
        return 0

    if args.agent is not None and args.directory is not None:
        raise UsageError("name an agent or pass --dir, not both")

    agent = None
    label = "custom"
    if args.directory is not None:
        root = Path(validation.text(args.directory, field="--dir", max_length=MAX_ROOT_CHARS))
    elif args.agent is not None:
        name = validation.text(args.agent, field="agent", max_length=64)
        agent = find_agent(name)
        if agent is None:
            known = ", ".join(item.name for item in CODING_AGENTS)
            raise UsageError(f"unknown agent {name!r}; known agents are {known}")
        root = agent.skill_root
        label = agent.label
    else:
        raise UsageError("name an agent to install into, or pass --dir; `--list` prints every known agent")

    try:
        result = install_skill(root, agent=agent.name if agent else None, force=args.force)
    except NotADirectoryError as error:
        print(f"{parser.prog}: {error}", file=sys.stderr)
        return 1
    except SkillRefusedError as error:
        print(f"{parser.prog}: {error}; re-run with --force to replace it", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "agent": result.agent,
                    "path": str(result.path),
                    "root": str(result.root),
                    "state": result.state,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"{STATE_LABELS[result.state]} for {label}: {result.path}")
    return 0


def _print_agents(agents: Sequence[CodingAgent]) -> None:
    """Print one line per supported agent, naming the root it reads."""
    width = max(len(agent.name) for agent in agents)
    for agent in agents:
        print(f"{agent.name.ljust(width)}  {agent.label}  {agent.skill_root}")
    print("\nAny other harness: `zett install --dir PATH` writes below that skill root.")

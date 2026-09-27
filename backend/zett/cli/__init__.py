"""Zett's command line: one module per command, imported when it runs.

The console script and ``python -m zett.cli`` both call :func:`main`. Parsing
stops at the command name: :func:`main` looks the name up, imports the module
that implements it, and hands the remaining arguments over, so ``zett --help``
imports nothing but this file and a command pays for the server, the scheduler,
or the agent runtime only when it actually runs.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

PROGRAM_NAME = "zett"
#: One-line introduction, identical to the README tagline and the project's
#: packaged ``description`` so `zett --help`, the README, and the PyPI page
#: introduce the product the same way.
PROGRAM_DESCRIPTION = (
    "A local-first, AI-assisted workspace for turning fleeting thoughts, "
    "conversations, links, and assets into reusable knowledge."
)
HELP_OPTIONS = frozenset({"-h", "--help"})


@dataclass(frozen=True, slots=True)
class Command:
    """One command: where it lives, what it is called here, and its one-liner."""

    name: str
    module: str
    #: What ``zett --help`` prints for the command. An internal role leaves it
    #: unset, so the listing describes what a user runs and nothing else.
    help: str | None = None
    #: Name of the callable in ``module`` that runs the command.
    entry: str = "main"


#: Every command this CLI dispatches, in listing order.
COMMANDS: tuple[Command, ...] = (
    Command("start", "zett.cli.start", "Serve the API and the frontend, detached by default"),
    Command("status", "zett.cli.status", "Report whether Zett is running"),
    Command("stop", "zett.cli.stop", "Stop the running Zett server"),
    Command("artifact", "zett.cli.artifact", "Create, read, and list artifacts that belong to no conversation"),
    Command("tag", "zett.cli.tag", "Manage library tags and the tags an artifact carries"),
    Command("install", "zett.cli.install", "Install Zett's skill into Claude Code, Codex, or another agent"),
    Command("scheduler", "zett.cli.role", entry="run_scheduler"),
    Command("worker", "zett.cli.role", entry="run_worker"),
)
COMMANDS_BY_NAME = {command.name: command for command in COMMANDS}


def command_names() -> list[str]:
    """Return every dispatched command name, in listing order."""
    return [command.name for command in COMMANDS]


def main(argv: Sequence[str] | None = None) -> int:
    """Jump to one command module and return its exit status.

    The module owns its parser, so its ``--help`` and its usage errors are
    rendered by the code that knows the options. Logging is configured after
    the command is known and before it runs, so ``--help`` and an unknown
    command neither create the log directory nor print a line above the usage.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in HELP_OPTIONS:
        print(parser_help())
        return 0
    command = COMMANDS_BY_NAME.get(arguments[0])
    if command is None:
        print(f"{PROGRAM_NAME}: error: unknown command {arguments[0]!r}", file=sys.stderr)
        print(f"{PROGRAM_NAME}: commands are {', '.join(command_names())}", file=sys.stderr)
        return 2
    from ..infra.log import configure_logging

    configure_logging()
    entry: Callable[[Sequence[str] | None], int] = getattr(importlib.import_module(command.module), command.entry)
    return entry(arguments[1:])


def parser_help() -> str:
    """Render the root help text without importing a command module."""
    return build_parser().format_help()


def build_parser() -> argparse.ArgumentParser:
    """Build the root parser ``zett --help`` renders.

    Its subparsers carry nothing but a help string: the module named next to
    each command parses that command, which is why this parser can describe
    every command without importing one.
    """
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description=PROGRAM_DESCRIPTION)
    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMMANDS:
        if command.help is not None:
            subcommands.add_parser(command.name, help=command.help, add_help=False)
    return parser


if __name__ == "__main__":
    sys.exit(main())

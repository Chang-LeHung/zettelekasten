"""Inspect the git state of a session-owned LaTeX project directory.

Zett owns no part of the project history: the Agent initializes the repository,
keeps a ``.gitignore``, and authors every commit with the shell. This adapter
only answers what git reports, so publishing an artifact can require a clean
tree without Zett writing history nobody described.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..scheduler.process_platform import helper_process_kwargs

#: Variables that redirect git when Zett itself runs inside another git process.
_REDIRECTING_ENVIRONMENT_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_QUARANTINE_PATH",
)

COMMAND_TIMEOUT_SECONDS = 30.0


class GitProjectError(RuntimeError):
    """Raised when the git executable is missing or one git command fails."""


def repository_root(directory: Path) -> Path | None:
    """Return the repository that contains the directory, if there is one."""
    completed = _git(directory, "rev-parse", "--show-toplevel", check=False)
    if completed.returncode != 0:
        return None
    root = completed.stdout.strip()
    return Path(root) if root else None


def is_repository(directory: Path) -> bool:
    """Return whether the directory already belongs to a git repository."""
    return repository_root(directory) is not None


def project_changes(directory: Path) -> tuple[str, ...]:
    """Return the project subtree's pending paths, or nothing outside a repository."""
    if not is_repository(directory):
        return ()
    output = _git(directory, "status", "--porcelain", "--untracked-files=all", "--", ".").stdout
    return tuple(line[3:].strip().strip('"') for line in output.splitlines() if line.strip())


def _environment() -> dict[str, str]:
    """Return a git environment that cannot be redirected by an enclosing process."""
    # Windows environment names are case-insensitive, so the filter must be too.
    environment = {key: value for key, value in os.environ.items() if key.upper() not in _REDIRECTING_ENVIRONMENT_KEYS}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _git(directory: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one git command inside the directory without leaking another repository."""
    try:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=directory,
            env=_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
            **helper_process_kwargs(),
        )
    except FileNotFoundError as error:
        raise GitProjectError("git is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise GitProjectError(f"git {' '.join(arguments)} timed out") from error
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}"
        raise GitProjectError(f"git {' '.join(arguments)} failed: {detail}")
    return completed


__all__ = [
    "GitProjectError",
    "is_repository",
    "project_changes",
    "repository_root",
]

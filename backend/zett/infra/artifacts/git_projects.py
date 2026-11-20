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

from zett.infra.log import get_logger

from ..scheduler.process_platform import helper_process_kwargs

logger = get_logger(__name__)

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


class GitRevertConflictError(GitProjectError):
    """Raised when reverting a range conflicts; the revert has been aborted."""


#: Author used for the restore commit only when the repository has no identity.
FALLBACK_IDENTITY = ("-c", "user.name=Zett Restore", "-c", "user.email=restore@zett.local")


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


def head_commit(directory: Path) -> str:
    """Return the full hash of HEAD, raising when there is no commit."""
    return _git(directory, "rev-parse", "--verify", "HEAD").stdout.strip()


def commits_between(directory: Path, base: str, head: str = "HEAD") -> int:
    """Return how many commits ``base..head`` holds."""
    return int(_git(directory, "rev-list", "--count", f"{base}..{head}").stdout.strip())


def is_ancestor(directory: Path, base: str, head: str = "HEAD") -> bool:
    """Return whether ``base`` is an ancestor of ``head``; a missing commit is not."""
    completed = _git(directory, "merge-base", "--is-ancestor", base, head, check=False)
    if completed.returncode in (0, 1):
        return completed.returncode == 0
    return False


def has_merge_commits(directory: Path, base: str, head: str = "HEAD") -> bool:
    """Return whether a merge commit lies in ``base..head``."""
    return int(_git(directory, "rev-list", "--merges", "--count", f"{base}..{head}").stdout.strip()) > 0


def _identity(directory: Path) -> tuple[str, ...]:
    """Return fallback ``-c`` arguments only when the repository has no usable identity."""
    for key in ("user.name", "user.email"):
        if not _git(directory, "config", key, check=False).stdout.strip():
            return FALLBACK_IDENTITY
    return ()


def _is_clean_at(directory: Path, head: str) -> bool:
    """Return whether HEAD is ``head``, nothing is pending, and no revert is in progress."""
    if head_commit(directory) != head:
        return False
    if _git(directory, "status", "--porcelain", "--untracked-files=all").stdout.strip():
        return False
    return _git(directory, "rev-parse", "-q", "--verify", "REVERT_HEAD", check=False).returncode != 0


def _recover(directory: Path, head: str) -> None:
    """Put the repository back at ``head`` with a clean tree, proving it rather than trusting abort."""
    _git(directory, "revert", "--abort", check=False)
    current = head_commit(directory)
    if current != head:
        # HEAD moved forward since entry; a hard reset would discard someone's commit.
        logger.error("Revert recovery refused; HEAD moved from %s to %s", head, current)
        raise GitRevertConflictError("The project changed during the restore and needs a manual look")
    try:
        if _is_clean_at(directory, head):
            return
    except GitProjectError:
        pass
    _git(directory, "reset", "--hard", head, check=False)


def revert_range(directory: Path, base: str, head: str, message: str) -> str:
    """Undo exactly ``base..head`` in one new commit that keeps every original commit.

    ``head`` is pinned by the caller, so a commit that lands after the caller
    counted the range is not reverted. Returns the new commit's hash. A failure
    restores the repository to the HEAD it had on entry (verified, with a hard
    reset when ``git revert --abort`` did not suffice) and raises
    ``GitRevertConflictError``.
    """
    identity = _identity(directory)
    entry = head_commit(directory)
    completed = _git(directory, "revert", "--no-commit", f"{base}..{head}", check=False)
    if completed.returncode != 0:
        _recover(directory, entry)
        detail = (completed.stderr or completed.stdout).strip()
        raise GitRevertConflictError(f"git revert failed: {detail}")
    try:
        _git(directory, *identity, "commit", "--allow-empty", "-m", message)
    except GitProjectError:
        _recover(directory, entry)
        raise
    return head_commit(directory)


def path_in_commit(directory: Path, commit: str, path: str) -> bool:
    """Return whether ``commit`` tracks ``path``."""
    return _git(directory, "cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0


def is_ignored(directory: Path, path: str) -> bool:
    """Return whether git ignores ``path`` (exit 0 ignored, 1 not, anything else is an error)."""
    completed = _git(directory, "check-ignore", "-q", "--", path, check=False)
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    detail = (completed.stderr or completed.stdout).strip() or f"exit code {completed.returncode}"
    raise GitProjectError(f"git check-ignore failed: {detail}")


def amend_with_path(directory: Path, path: str, expected_head: str) -> str | None:
    """Fold one tracked file's pending change into ``expected_head``; return the new sha or None.

    Nothing is amended when HEAD is no longer the commit the caller created, so
    a commit someone else made meanwhile is never rewritten.
    """
    if head_commit(directory) != expected_head:
        logger.warning("Skipped the PDF amend; HEAD moved since the revert commit %s", expected_head)
        return None
    if not _git(directory, "status", "--porcelain", "--", path).stdout.strip():
        return None
    if _git(directory, "ls-files", "--error-unmatch", "--", path, check=False).returncode != 0:
        return None
    _git(directory, "add", "--", path)
    _git(directory, *_identity(directory), "commit", "--amend", "--no-edit")
    return head_commit(directory)


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
    "FALLBACK_IDENTITY",
    "GitProjectError",
    "GitRevertConflictError",
    "amend_with_path",
    "commits_between",
    "has_merge_commits",
    "path_in_commit",
    "head_commit",
    "is_ancestor",
    "revert_range",
    "is_repository",
    "project_changes",
    "repository_root",
]

"""Require a committed LaTeX project before its artifact becomes the saved one.

A LaTeX PDF artifact owns a project directory rather than an inline body, so its
real content is the files the Agent keeps there. The Agent also owns that
history: it initializes the repository, ignores the regenerated build files, and
commits each meaningful change with its own Conventional Commit message. Zett
neither commits nor prepares anything; publishing only verifies that the project
is a git repository without pending changes, so a saved artifact always names a
revision instead of an unrecorded working tree.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...infra.artifacts.git_projects import (
    GitProjectError,
    is_repository,
    project_changes,
)
from ...infra.files.object_store import get_object_store
from ...infra.log import get_logger
from ...schemas import AgentArtifactEntity, ArtifactType, LatexPdfArtifactContent

logger = get_logger(__name__)

#: Failures that mean "cannot ask git", never "the project is dirty".
_GIT_FAILURES = (GitProjectError, OSError, ValueError)

#: Pending paths named in one failure message before the list is elided.
_REPORTED_CHANGES = 5


class UncommittedLatexProjectError(RuntimeError):
    """Raised when a LaTeX project is not a clean git revision."""


class ArtifactVersioning:
    """Verify the git revision behind one LaTeX PDF artifact.

    A git that cannot be run is contained at this boundary: inspecting is not
    something a user can repair from the save dialog, so the verification warns
    and lets the save through rather than inventing a failure. A project git can
    answer about is enforced exactly: it must be a repository, and it must have
    nothing pending.
    """

    async def verify(self, artifact: AgentArtifactEntity) -> tuple[str, ...]:
        """Return the pending paths, raising while the project is not a clean revision.

        Only an existing project directory is inspected; an artifact whose
        directory is gone has no working tree to publish from.
        """
        directory = self._project_directory(artifact)
        if directory is None:
            return ()
        try:
            tracked = await asyncio.to_thread(is_repository, directory)
            pending = await asyncio.to_thread(project_changes, directory) if tracked else ()
        except _GIT_FAILURES as error:
            self._warn(artifact, error)
            return ()
        if not tracked:
            raise UncommittedLatexProjectError(
                "The LaTeX project is not a git repository. "
                "Initialize it and commit its sources before saving the artifact."
            )
        if pending:
            raise UncommittedLatexProjectError(
                "The LaTeX project has uncommitted changes: "
                f"{_summarize(pending)}. Commit them before saving the artifact."
            )
        return pending

    def _project_directory(self, artifact: AgentArtifactEntity) -> Path | None:
        """Return the artifact's project directory when it is an existing LaTeX project."""
        content = artifact.editable_content
        if artifact.artifact_type != ArtifactType.LATEX_PDF or not isinstance(content, LatexPdfArtifactContent):
            return None
        directory = get_object_store().resolve(content.project_path)
        return directory if directory.is_dir() else None

    @staticmethod
    def _warn(artifact: AgentArtifactEntity, error: Exception) -> None:
        """Report one contained git failure without inventing a result for the tree."""
        content = artifact.editable_content
        project_path = content.project_path if isinstance(content, LatexPdfArtifactContent) else "unknown"
        logger.warning(
            "Could not inspect the LaTeX project git state; artifact_id=%s project_path=%s error=%s",
            artifact.id,
            project_path,
            error,
        )


def _summarize(pending: tuple[str, ...]) -> str:
    """Name the pending paths, eliding the tail of a long list."""
    if len(pending) <= _REPORTED_CHANGES:
        return ", ".join(pending)
    return f"{', '.join(pending[:_REPORTED_CHANGES])} and {len(pending) - _REPORTED_CHANGES} more"


artifact_versioning = ArtifactVersioning()

__all__ = ["ArtifactVersioning", "UncommittedLatexProjectError", "artifact_versioning"]

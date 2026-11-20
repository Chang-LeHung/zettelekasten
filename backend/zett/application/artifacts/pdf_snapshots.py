"""Keep the PDF a LaTeX artifact had at its last save, for a before/after view."""

import asyncio
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from zett.application.files.object_store import join_object_key, latex_snapshot_key, object_url
from zett.infra.artifacts import git_projects as git
from zett.infra.artifacts import pdf_snapshots as files
from zett.infra.artifacts.latex_projects import latex_pdf_path
from zett.infra.files.object_store import get_object_store
from zett.infra.log import get_logger
from zett.schemas import AgentArtifactEntity, ArtifactType, LatexPdfArtifactContent

logger = get_logger(__name__)


class PdfComparison(BaseModel):
    """Read model of one artifact's saved and current PDF."""

    base_url: str | None
    base_saved_at: datetime | None
    target_url: str | None
    stale: bool
    #: Commits between the commit recorded at the last save and HEAD; None when
    #: none was recorded or git cannot answer.
    commits_since: int | None = None
    #: True when the saved commit is still an ancestor of HEAD and newer commits exist.
    can_restore: bool = False


class PdfRestoration(PdfComparison):
    """Comparison after a restore, with the number of commits it undid."""

    restored_commits: int


class LatexRestoreError(RuntimeError):
    """Raised when the saved version cannot be restored; the message says why."""


#: Failures that mean "cannot ask git".
_GIT_FAILURES = (git.GitProjectError, OSError, ValueError)

RESTORE_MESSAGE = "revert: restore the version saved by the user"


class PdfSnapshotService:
    """Snapshot on save, compare on read; failures never reach the save."""

    @staticmethod
    def _content(artifact: AgentArtifactEntity) -> LatexPdfArtifactContent | None:
        content = artifact.editable_content
        if artifact.artifact_type != ArtifactType.LATEX_PDF or not isinstance(content, LatexPdfArtifactContent):
            return None
        return content

    async def head(self, artifact: AgentArtifactEntity) -> str | None:
        """Return the project's HEAD, or None for a non-LaTeX artifact or when git cannot answer."""
        content = self._content(artifact)
        if content is None:
            return None
        directory = get_object_store().resolve(content.project_path)
        try:
            return await asyncio.to_thread(git.head_commit, directory)
        except _GIT_FAILURES as error:
            logger.warning("Could not read the git HEAD; artifact_id=%s error=%s", artifact.id, error)
            return None

    async def capture(self, artifact: AgentArtifactEntity, commit: str | None = None) -> None:
        """Copy the current compiled PDF over the snapshot and record the saved commit.

        ``commit`` is the HEAD the caller verified; ``save`` passes the one it saw
        after its clean-tree check. Without it (the user-edit ``PUT`` path) HEAD is
        read here, at capture time. A source PDF that is invalid or truncated
        deletes the stale snapshot, so the saved version has no usable PDF
        (``base_url`` is null) while the sidecar still records commit and time.
        """
        content = self._content(artifact)
        if content is None:
            return
        copied = False
        try:
            source = latex_pdf_path(artifact.session_id, content)
            destination = get_object_store().resolve(latex_snapshot_key(artifact.session_id, artifact.id))
            copied = await asyncio.to_thread(files.copy_atomically, source, destination)
        except Exception as error:  # noqa: BLE001 - a snapshot must never fail a save
            logger.warning("Skipped LaTeX PDF snapshot; artifact_id=%s error=%s", artifact.id, error)
        if not copied:
            # The (PDF, commit) pair is atomic: no copy means no older PDF beside the new commit.
            await self._remove_snapshot(artifact)
        if commit is None:
            commit = await self.head(artifact)
        await self._record_commit(artifact, commit)

    @staticmethod
    async def _remove_snapshot(artifact: AgentArtifactEntity) -> None:
        try:
            destination = get_object_store().resolve(latex_snapshot_key(artifact.session_id, artifact.id))
            await asyncio.to_thread(destination.unlink, missing_ok=True)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not remove the stale LaTeX PDF snapshot; artifact_id=%s error=%s", artifact.id, error)

    async def _record_commit(
        self, artifact: AgentArtifactEntity, commit: str | None, saved_at: datetime | None = None
    ) -> None:
        """Store the save time (now unless given) and the commit beside the snapshot."""
        try:
            snapshot = get_object_store().resolve(latex_snapshot_key(artifact.session_id, artifact.id))
            await asyncio.to_thread(files.write_commit, snapshot, commit, saved_at)
        except Exception as error:  # noqa: BLE001 - recording must never fail a save
            logger.warning("Could not record the saved git commit; artifact_id=%s error=%s", artifact.id, error)

    async def discard(self, artifact: AgentArtifactEntity) -> None:
        """Remove the snapshot of a deleted artifact; failures are logged only."""
        try:
            key = latex_snapshot_key(artifact.session_id, artifact.id)
            await get_object_store().delete(key)
            await asyncio.to_thread(files.remove_commit, get_object_store().resolve(key))
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not remove LaTeX PDF snapshot; artifact_id=%s error=%s", artifact.id, error)

    async def compare(self, artifact: AgentArtifactEntity) -> PdfComparison:
        """Describe the saved snapshot, the current PDF, and whether sources are newer.

        Raises ``ValueError`` when the artifact is not a LaTeX PDF artifact.
        """
        content = self._content(artifact)
        if content is None:
            raise ValueError("Artifact is not a LaTeX PDF")
        store = get_object_store()
        base_key = latex_snapshot_key(artifact.session_id, artifact.id)
        base_path = store.resolve(base_key)
        base_saved_at = await asyncio.to_thread(self._saved_at, base_path)
        directory = store.resolve(content.project_path)
        try:
            target = latex_pdf_path(artifact.session_id, content)
        except (ValueError, OSError):
            target = None
        target_time = await asyncio.to_thread(files.modified_at, target) if target is not None else None
        stale = target_time is not None and await asyncio.to_thread(
            files.has_newer_source, directory, target_time.timestamp()
        )
        commits_since, can_restore = await self._commits_since(directory, files.read_commit(base_path))
        return PdfComparison(
            base_url=object_url(base_key) if base_saved_at is not None else None,
            base_saved_at=base_saved_at,
            target_url=object_url(join_object_key(content.project_path, content.pdf_name))
            if target is not None
            else None,
            stale=stale,
            commits_since=commits_since,
            can_restore=can_restore,
        )

    @staticmethod
    def _saved_at(snapshot: Path) -> datetime | None:
        """Return when the user saved: the sidecar's time, else an old snapshot's mtime."""
        if not snapshot.is_file():
            return None
        return files.read_saved_at(snapshot) or files.modified_at(snapshot)

    @staticmethod
    async def _commits_since(directory: Path, saved: str | None) -> tuple[int | None, bool]:
        """Count commits after the saved one and tell whether restoring is possible."""
        if saved is None:
            return None, False
        try:
            count = await asyncio.to_thread(git.commits_between, directory, saved)
            ancestor = await asyncio.to_thread(git.is_ancestor, directory, saved)
        except _GIT_FAILURES:
            return None, False
        return count, ancestor and count > 0

    async def restore(self, artifact: AgentArtifactEntity) -> PdfRestoration:
        """Undo every commit made since the last save with one new revert commit.

        History is kept. Raises ``LatexRestoreError`` when the artifact is not a
        LaTeX PDF, nothing was recorded at save, the saved commit left HEAD's
        history, the tree is dirty, a merge lies in the range, or the revert
        conflicts (which leaves the tree untouched).
        """
        content = self._content(artifact)
        if content is None:
            raise LatexRestoreError("Artifact is not a LaTeX PDF")
        store = get_object_store()
        directory = store.resolve(content.project_path)
        snapshot = store.resolve(latex_snapshot_key(artifact.session_id, artifact.id))
        saved = files.read_commit(snapshot)
        if saved is None:
            raise LatexRestoreError("No saved version is recorded; save the artifact first")
        saved_at = await asyncio.to_thread(self._saved_at_or_sidecar, snapshot)
        try:
            restored, revert_commit = await asyncio.to_thread(self._revert, directory, saved)
        except git.GitRevertConflictError as error:
            logger.warning("LaTeX restore conflicted; artifact_id=%s error=%s", artifact.id, error)
            raise LatexRestoreError("Could not restore automatically: reverting the changes conflicts") from error
        except _GIT_FAILURES as error:
            logger.warning("LaTeX restore failed; artifact_id=%s error=%s", artifact.id, error)
            raise LatexRestoreError(f"Could not restore the saved version: {error}") from error
        amended = await self._restore_pdf(content, snapshot, directory, revert_commit, saved)
        # The project now matches what was saved: the amended commit, else the revert commit.
        # The saved time stays the user's original save: only the commit moves. If the
        # PDF copy-back failed, the disk PDF may lag the sources until recompiled.
        new_commit = amended or revert_commit
        head = await self.head(artifact)
        if head is None:
            logger.warning(
                "Could not read HEAD after the restore; recording the commit it created; artifact_id=%s", artifact.id
            )
        elif head != new_commit:
            raise LatexRestoreError("The project changed during the restore; check it before saving again")
        await self._record_commit(artifact, new_commit, saved_at)
        comparison = await self.compare(artifact)
        return PdfRestoration(**comparison.model_dump(), restored_commits=restored)

    @staticmethod
    def _saved_at_or_sidecar(snapshot: Path) -> datetime | None:
        return files.read_saved_at(snapshot) or files.modified_at(snapshot)

    @staticmethod
    def _revert(directory: Path, saved: str) -> tuple[int, str]:
        if git.project_changes(directory):
            raise LatexRestoreError("The project has uncommitted changes; commit or discard them first")
        # HEAD is read once, after the clean-tree check; count and revert both use it.
        head = git.head_commit(directory)
        if not git.is_ancestor(directory, saved, head):
            raise LatexRestoreError("The saved version is no longer part of the project history")
        count = git.commits_between(directory, saved, head)
        if count == 0:
            raise LatexRestoreError("Nothing changed since the last save")
        if git.has_merge_commits(directory, saved, head):
            raise LatexRestoreError("A merge commit lies in the range; restore it manually")
        return count, git.revert_range(directory, saved, head, RESTORE_MESSAGE)

    @staticmethod
    async def _restore_pdf(
        content: LatexPdfArtifactContent, snapshot: Path, directory: Path, revert_commit: str, saved: str
    ) -> str | None:
        """Put the saved PDF back so the preview matches; return the amended commit or None.

        When the saved commit does not track the PDF the copy happens only if git
        ignores it (so no untracked file is left). A failure is only logged.
        """
        if not snapshot.is_file():
            return None
        try:
            destination = directory / content.pdf_name
            if destination.parent.resolve() != directory.resolve() or destination.is_symlink():
                raise ValueError("PDF must stay inside the project")
            if not await asyncio.to_thread(git.path_in_commit, directory, saved, content.pdf_name):
                # Absent because deleted: leave it. Absent because ignored: the copy
                # cannot dirty the tree, so put the saved PDF back without an amend.
                if await asyncio.to_thread(git.is_ignored, directory, content.pdf_name):
                    await asyncio.to_thread(files.copy_atomically, snapshot, destination)
                return None
            await asyncio.to_thread(files.copy_atomically, snapshot, destination)
            return await asyncio.to_thread(git.amend_with_path, directory, content.pdf_name, revert_commit)
        except _GIT_FAILURES as error:
            logger.warning("Could not restore the saved PDF; project_path=%s error=%s", content.project_path, error)
            return None


pdf_snapshot_service = PdfSnapshotService()

__all__ = ["LatexRestoreError", "PdfComparison", "PdfRestoration", "PdfSnapshotService", "pdf_snapshot_service"]

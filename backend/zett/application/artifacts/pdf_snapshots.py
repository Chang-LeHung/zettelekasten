"""Keep the PDF a LaTeX artifact had at its last save, for a before/after view."""

import asyncio
from datetime import datetime

from pydantic import BaseModel

from zett.application.files.object_store import latex_snapshot_key, object_url
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


class PdfSnapshotService:
    """Snapshot on save, compare on read; failures never reach the save."""

    @staticmethod
    def _content(artifact: AgentArtifactEntity) -> LatexPdfArtifactContent | None:
        content = artifact.editable_content
        if artifact.artifact_type != ArtifactType.LATEX_PDF or not isinstance(content, LatexPdfArtifactContent):
            return None
        return content

    async def capture(self, artifact: AgentArtifactEntity) -> None:
        """Copy the current compiled PDF over the snapshot; skip and log when unusable."""
        content = self._content(artifact)
        if content is None:
            return
        try:
            source = latex_pdf_path(artifact.session_id, content)
            destination = get_object_store().resolve(latex_snapshot_key(artifact.session_id, artifact.id))
            await asyncio.to_thread(files.copy_atomically, source, destination)
        except Exception as error:  # noqa: BLE001 - a snapshot must never fail a save
            logger.warning("Skipped LaTeX PDF snapshot; artifact_id=%s error=%s", artifact.id, error)

    async def discard(self, artifact: AgentArtifactEntity) -> None:
        """Remove the snapshot of a deleted artifact; failures are logged only."""
        try:
            await get_object_store().delete(latex_snapshot_key(artifact.session_id, artifact.id))
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
        base_saved_at = await asyncio.to_thread(files.modified_at, base_path)
        try:
            target = latex_pdf_path(artifact.session_id, content)
        except (ValueError, OSError):
            target = None
        stale = False
        if target is not None:
            stale = await asyncio.to_thread(
                files.has_newer_source, store.resolve(content.project_path), target.stat().st_mtime
            )
        return PdfComparison(
            base_url=object_url(base_key) if base_saved_at is not None else None,
            base_saved_at=base_saved_at,
            target_url=store.url(f"{content.project_path}/{content.pdf_name}") if target is not None else None,
            stale=stale,
        )


pdf_snapshot_service = PdfSnapshotService()

__all__ = ["PdfComparison", "PdfSnapshotService", "pdf_snapshot_service"]

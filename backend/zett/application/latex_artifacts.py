"""Serve the compiled document referenced by a LaTeX artifact."""

from pathlib import Path

from ..infra.dao import artifact_storage
from ..infra.latex_projects import latex_pdf_path
from ..schemas import LatexPdfArtifactContent


def get_latex_pdf(session_id: str, artifact_id: str) -> Path | None:
    artifact = artifact_storage.get_for_session(session_id, artifact_id)
    if artifact is None or not isinstance(artifact.content, LatexPdfArtifactContent):
        raise FileNotFoundError("LaTeX PDF artifact not found")
    try:
        return latex_pdf_path(session_id, artifact.content)
    except FileNotFoundError:
        # The project is registered before the Agent writes or compiles any files.
        # Absence is an ordinary not-ready state, distinct from a nonexistent artifact.
        return None

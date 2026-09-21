"""Resolve existing session-owned LaTeX projects without copying their files."""

from pathlib import Path
from uuid import UUID

from ...application.files.object_store import ObjectKey, latex_project_key
from ...schemas import LatexPdfArtifactContent, LatexPdfArtifactCreate
from ..files.object_store import get_object_store


def create_latex_project(session_id: str, content: LatexPdfArtifactCreate) -> LatexPdfArtifactContent:
    """Allocate a relative project key before the Agent writes or compiles files."""
    if str(UUID(session_id)) != session_id:
        raise ValueError("Session ID must be a canonical UUID")
    key = latex_project_key(session_id, content.title)
    project = get_object_store().ensure_directory(key)
    # Reuse existing directories without overwriting any source or compiled files.
    if not project.is_dir():
        raise ValueError("Project path already exists and is not a directory")
    return LatexPdfArtifactContent(project_path=str(key), pdf_name=content.pdf_name)


def validate_latex_project_path(session_id: str, content: LatexPdfArtifactContent) -> ObjectKey:
    """Require the exact relative project key; ObjectStore owns containment checks."""
    canonical_id = str(UUID(session_id))
    if canonical_id != session_id:
        raise ValueError("Session ID must be a canonical UUID")
    project = ObjectKey(content.project_path)
    expected = latex_project_key(canonical_id, content.title)
    if project.value != str(expected):
        raise ValueError("Project path must be the canonical artifacts/<session>/<title> object key")
    get_object_store().resolve(project)
    return project


def latex_pdf_path(session_id: str, content: LatexPdfArtifactContent) -> Path:
    """Validate actual PDF bytes only when serving a preview, not when saving metadata."""
    project = validate_latex_project_path(session_id, content)
    pdf_key = ObjectKey(f"{project}/{content.pdf_name}")
    pdf = get_object_store().resolve(pdf_key)
    if pdf.resolve() != pdf:
        raise ValueError("PDF must not resolve through a symbolic link")
    project_path = get_object_store().resolve(project)
    if not project_path.is_dir() or not pdf.is_file():
        raise FileNotFoundError("LaTeX project or compiled PDF not found")
    with pdf.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("The compiled file is not a PDF")
    return pdf

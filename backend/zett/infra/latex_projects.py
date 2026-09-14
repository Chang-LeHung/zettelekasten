"""Resolve existing session-owned LaTeX projects without copying their files."""

from pathlib import Path
from uuid import UUID

from ..config import settings
from ..schemas import LatexPdfArtifactContent, LatexPdfArtifactCreate


def create_latex_project(session_id: str, content: LatexPdfArtifactCreate) -> LatexPdfArtifactContent:
    """Allocate the directory first: the Agent needs its path before it can compile a PDF."""
    if str(UUID(session_id)) != session_id:
        raise ValueError("Session ID must be a canonical UUID")
    root = settings.artifact_directory.expanduser().resolve()
    project = root / session_id / content.title
    if project.resolve() != project:
        raise ValueError("Project directory must not use symbolic links")
    if project.exists() and not project.is_dir():
        raise ValueError("Project path already exists and is not a directory")
    # Reuse existing directories without overwriting any source or compiled files.
    project.mkdir(parents=True, exist_ok=True)
    return LatexPdfArtifactContent(project_path=str(project), pdf_name=content.pdf_name)


def validate_latex_project_path(session_id: str, content: LatexPdfArtifactContent) -> Path:
    """Require the exact project layout and reject symlink escapes at every level."""
    canonical_id = str(UUID(session_id))
    if canonical_id != session_id:
        raise ValueError("Session ID must be a canonical UUID")
    root = settings.artifact_directory.expanduser().resolve()
    expected = root / canonical_id / content.title
    project = Path(content.project_path).expanduser().absolute()
    if project != expected or project.resolve() != expected:
        raise ValueError("Project must be under the session artifacts directory, in a folder named after the PDF stem")
    return expected


def latex_pdf_path(session_id: str, content: LatexPdfArtifactContent) -> Path:
    """Validate actual PDF bytes only when serving a preview, not when saving metadata."""
    expected = validate_latex_project_path(session_id, content)
    pdf = expected / content.pdf_name
    if pdf.resolve() != pdf:
        raise ValueError("PDF must not resolve outside its project path")
    if not expected.is_dir() or not pdf.is_file():
        raise FileNotFoundError("LaTeX project or compiled PDF not found")
    with pdf.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError("The compiled file is not a PDF")
    return pdf

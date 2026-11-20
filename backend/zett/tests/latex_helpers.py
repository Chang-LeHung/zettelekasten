"""Shared fixtures-as-functions for the LaTeX artifact tests; not a test module."""

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from zett.application.files.object_store import latex_snapshot_key
from zett.infra.files.object_store import get_object_store
from zett.infra.persistence.dao import session_storage
from zett.schemas import AgentSessionCreate

PDF_ONE = b"%PDF-1.4\none\n%%EOF\n"
PDF_TWO = b"%PDF-1.4\ntwo\n%%EOF\n"

#: Build output the Agent's own project ``.gitignore`` is expected to cover.
LATEX_GITIGNORE = "*.aux\n*.log\n*.out\n*.toc\n*.synctex.gz\n"
AGENT_IDENTITY = ("-c", "user.name=Agent", "-c", "user.email=agent@example.com")


def git_result(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *arguments), cwd=directory, capture_output=True, text=True)


def git(directory: Path, *arguments: str) -> str:
    completed = git_result(directory, *arguments)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def status(directory: Path) -> str:
    """Return the project subtree's pending changes, ignoring build output."""
    return git(directory, "status", "--porcelain", "--", ".").strip()


def subjects(directory: Path) -> list[str]:
    return git(directory, "log", "--pretty=%s").splitlines()


def initialize(directory: Path, message: str = "chore(paper): start project", gitignore: str = LATEX_GITIGNORE) -> None:
    """Do what the Agent does with the shell: init, ignore build output, and commit."""
    git(directory, "init", "-q", "-b", "main", ".")
    (directory / ".gitignore").write_text(gitignore, encoding="utf-8")
    commit(directory, message)


def commit(directory: Path, message: str = "docs(paper): add introduction") -> None:
    """Commit pending project changes the way the Agent's shell command does."""
    git(directory, "add", "-A")
    git(directory, *AGENT_IDENTITY, "commit", "-q", "-m", message)


def project_directory(session_id: str, name: str = "paper") -> Path:
    return get_object_store().resolve(f"artifacts/{session_id}/{name}")


def create_pdf_artifact(client: TestClient, session_id: str, pdf_name: str = "paper.pdf") -> dict[str, object]:
    response = client.post(
        f"/api/agent/{session_id}/artifacts",
        json={"content": {"artifact_type": "latex_pdf", "pdf_name": pdf_name}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def write_sources(directory: Path, name: str = "paper") -> None:
    """Write one source file and the build files a LaTeX run regenerates."""
    (directory / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
    (directory / f"{name}.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    for build_file in ("paper.aux", "paper.log", "paper.toc"):
        (directory / build_file).write_text("generated")


def save(client: TestClient, session_id: str, artifact_id: object) -> object:
    return client.post(f"/api/agent/{session_id}/artifacts/{artifact_id}/save")


def snapshot_path(session_id: str, artifact_id: object) -> Path:
    return get_object_store().resolve(latex_snapshot_key(session_id, str(artifact_id)))


async def prepared_project(client: TestClient, gitignore: str = LATEX_GITIGNORE) -> tuple[str, dict[str, object]]:
    """Create a session with a LaTeX artifact and a committed project."""
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = create_pdf_artifact(client, session_id)
    directory = project_directory(session_id)
    write_sources(directory)
    initialize(directory, gitignore=gitignore)
    return session_id, artifact

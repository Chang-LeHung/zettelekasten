"""LaTeX references use real temporary projects and an isolated SQLite database."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from zett.config import settings
from zett.infra import object_store as object_store_module
from zett.infra.dao import artifact_storage, session_storage
from zett.infra.database import session_scope
from zett.infra.object_store import LocalObjectStore, get_object_store
from zett.infra.tables import SessionArtifactRow
from zett.main import app
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArtifactListOptions,
    LatexPdfArtifactContent,
    LatexPdfArtifactCreate,
)


def project_key(session_id: str, name: str = "paper") -> str:
    return f"artifacts/{session_id}/{name}"


def project(session_id: str, name: str = "paper") -> dict[str, str]:
    key = project_key(session_id, name)
    directory = get_object_store().ensure_directory(key)
    (directory / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
    (directory / f"{name}.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    return {"artifact_type": "latex_pdf", "project_path": key, "pdf_name": f"{name}.pdf"}


async def test_latex_pdf_lifecycle_and_inline_content() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    content = project(session_id)
    endpoint = f"/api/agent/{session_id}/artifacts"
    with TestClient(app) as client:
        response = client.post(endpoint, json={"content": {"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"}})
        assert response.status_code == 201, response.text
        artifact = response.json()
        assert artifact["content"] == content
        assert artifact["artifact_type"] == "latex_pdf"
        async with session_scope() as db:
            rows = await db.scalars(select(SessionArtifactRow).where(SessionArtifactRow.id == artifact["id"]))
            row = rows.one()
            assert row.artifact_type == 5
            assert row.title == "paper"
            assert json.loads(row.content_json) == content
        url = f"{endpoint}/{artifact['id']}"
        pdf = client.get(artifact["content_url"])
        assert pdf.status_code == 200
        assert pdf.content == b"%PDF-1.4\n%%EOF\n"
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.headers["content-disposition"].startswith("inline;")
        replacement = project(session_id, "revised")
        updated = client.put(url, json={"content": replacement})
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        saved = client.post(f"{url}/save")
        assert saved.status_code == 200
        assert saved.json()["status"] == "saved"
        assert saved.json()["version"] == 3
        assert (
            len(await artifact_storage.list(ArtifactListOptions(query="revised", artifact_types=("latex_pdf",)))) == 1
        )
        assert client.get(url).json()["content"] == replacement
        other_session = (await session_storage.create(AgentSessionCreate())).session_id
        assert client.get(f"/api/agent/{other_session}/artifacts/{artifact['id']}").status_code == 404
        assert client.delete(url).json() == {"ok": True}
        assert client.get(artifact["content_url"]).status_code == 200
        # References do not own source files: deleting a record must not erase the user's project.
        assert (get_object_store().resolve(project_key(session_id)) / "main.tex").is_file()
        assert (get_object_store().resolve(project_key(session_id, "revised")) / "revised.pdf").is_file()


@pytest.mark.parametrize(
    "name", ["../paper.pdf", "/paper.pdf", "a\\b.pdf", "paper.tex", ".pdf", "...pdf", "paper\x00.pdf"]
)
def test_pdf_name_is_a_plain_filename(name: str) -> None:
    with pytest.raises(ValidationError):
        LatexPdfArtifactContent(project_path="artifacts/unused/paper", pdf_name=name)


@pytest.mark.parametrize("failure", ["outside", "symlink_project"])
async def test_invalid_project_cannot_be_registered(tmp_path, failure: str) -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    content = project(session_id)
    directory = get_object_store().resolve(project_key(session_id))
    if failure == "outside":
        content["project_path"] = "artifacts/outside/paper"
    else:
        target = tmp_path.parent / f"{session_id}-outside"
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
        del content["project_path"]
    with TestClient(app) as client:
        response = client.post(f"/api/agent/{session_id}/artifacts", json={"content": content})
        assert response.status_code == 422, response.text
    assert await artifact_storage.list(ArtifactListOptions(session_id=session_id)) == []


async def test_missing_pdf_does_not_block_metadata_or_saving() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    content = project(session_id)
    with TestClient(app) as client:
        endpoint = f"/api/agent/{session_id}/artifacts"
        artifact = client.post(
            endpoint, json={"content": {"artifact_type": "latex_pdf", "pdf_name": content["pdf_name"]}}
        ).json()
        (get_object_store().resolve(project_key(session_id)) / "paper.pdf").unlink()
        url = f"{endpoint}/{artifact['id']}"
        assert client.get(artifact["content_url"]).status_code == 404
        assert client.get(url).status_code == 200
        assert client.put(url, json={"content": content}).status_code == 200
        assert client.post(f"{url}/save").status_code == 200


async def test_create_allocates_directory_before_agent_writes_files(tmp_path, monkeypatch) -> None:
    # A configured non-default root proves consumers must use the returned path.
    root = tmp_path / "custom-root"
    monkeypatch.setattr(settings, "storage_root", root)
    monkeypatch.setattr(object_store_module, "_object_store", LocalObjectStore(root))
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        endpoint = f"/api/agent/{session_id}/artifacts"
        response = client.post(endpoint, json={"content": {"artifact_type": "latex_pdf", "pdf_name": "report.pdf"}})
        assert response.status_code == 201, response.text
        artifact = response.json()
        assert artifact["content"]["project_path"] == project_key(session_id, "report")
        directory = get_object_store().resolve(artifact["content"]["project_path"])
        assert directory.is_dir()
        assert list(directory.iterdir()) == []
        stored = await artifact_storage.get(artifact["id"])
        assert stored is not None and stored.content.project_path == artifact["content"]["project_path"]
        url = f"{endpoint}/{artifact['id']}"
        assert client.get(artifact["content_url"]).status_code == 404
        assert client.put(url, json={"content": artifact["content"]}).status_code == 200
        assert client.post(f"{url}/save").status_code == 200
        (directory / "main.tex").write_text("Source created after the artifact")
        (directory / artifact["content"]["pdf_name"]).write_bytes(b"%PDF-1.4\n%%EOF\n")
        assert client.get(artifact["content_url"]).status_code == 200
        assert client.post(f"{url}/save").status_code == 200


async def test_storage_accepts_minimal_create_input_without_touching_existing_sources() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    content = project(session_id)
    result = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=LatexPdfArtifactCreate(pdf_name="paper.pdf"),
        )
    )
    assert result.content.project_path == content["project_path"]
    assert (get_object_store().resolve(project_key(session_id)) / "main.tex").read_text().startswith(r"\documentclass")


@pytest.mark.parametrize("failure", ["invalid_pdf", "symlink_pdf"])
async def test_preview_validates_pdf_after_creation(tmp_path, failure: str) -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = await artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=LatexPdfArtifactCreate(pdf_name="paper.pdf"),
        )
    )
    pdf = get_object_store().resolve(project_key(session_id)) / "paper.pdf"
    if failure == "invalid_pdf":
        pdf.write_bytes(b"not a PDF")
    else:
        outside = tmp_path.parent / f"{session_id}-outside.pdf"
        outside.write_bytes(b"%PDF-1.4\n%%EOF\n")
        pdf.symlink_to(outside)
    with TestClient(app) as client:
        assert client.get(artifact.content_url or "").status_code == 404

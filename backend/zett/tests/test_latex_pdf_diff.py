"""A LaTeX artifact keeps the PDF it had at its last save for a before/after view."""

import os

from fastapi.testclient import TestClient
from test_latex_git import (
    commit,
    create_pdf_artifact,
    initialize,
    project_directory,
    save,
    status,
    write_sources,
)

from zett.application.files.object_store import latex_snapshot_key
from zett.infra.files.object_store import get_object_store
from zett.infra.persistence.dao import session_storage
from zett.main import app
from zett.schemas import AgentSessionCreate

PDF_ONE = b"%PDF-1.4\none\n%%EOF\n"
PDF_TWO = b"%PDF-1.4\ntwo\n%%EOF\n"


async def prepared(client: TestClient) -> tuple[str, dict[str, object]]:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    artifact = create_pdf_artifact(client, session_id)
    directory = project_directory(session_id)
    write_sources(directory)
    initialize(directory)
    return session_id, artifact


def snapshot_path(session_id: str, artifact_id: object):
    return get_object_store().resolve(latex_snapshot_key(session_id, str(artifact_id)))


async def test_save_snapshots_and_second_save_replaces_it() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        directory = project_directory(session_id)
        assert save(client, session_id, artifact["id"]).status_code == 200
        path = snapshot_path(session_id, artifact["id"])
        assert path.read_bytes() == b"%PDF-1.4\n%%EOF\n"
        (directory / "paper.pdf").write_bytes(PDF_TWO)
        commit(directory)
        assert save(client, session_id, artifact["id"]).status_code == 200
        assert path.read_bytes() == PDF_TWO
        # The snapshot lives outside the project, so git stays clean.
        assert status(directory) == ""
        assert not list(path.parent.glob(".snapshot-*"))


async def test_save_succeeds_without_a_pdf_and_keeps_the_older_snapshot() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        directory = project_directory(session_id)
        assert save(client, session_id, artifact["id"]).status_code == 200
        (directory / "paper.pdf").unlink()
        commit(directory)
        assert save(client, session_id, artifact["id"]).status_code == 200
        assert snapshot_path(session_id, artifact["id"]).read_bytes() == b"%PDF-1.4\n%%EOF\n"
        (directory / "paper.pdf").write_bytes(b"not a pdf")
        commit(directory)
        assert save(client, session_id, artifact["id"]).status_code == 200
        assert snapshot_path(session_id, artifact["id"]).read_bytes() == b"%PDF-1.4\n%%EOF\n"


async def test_pdf_diff_before_and_after_save_and_stale() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        directory = project_directory(session_id)
        url = f"/api/artifacts/{artifact['id']}/pdf-diff"
        before = client.get(url)
        assert before.status_code == 200, before.text
        body = before.json()
        assert body["base_url"] is None and body["base_saved_at"] is None
        assert body["target_url"] == artifact["content_url"]
        assert body["stale"] is False
        assert save(client, session_id, artifact["id"]).status_code == 200
        body = client.get(url).json()
        assert body["base_url"] == f"/api/files/{latex_snapshot_key(session_id, str(artifact['id']))}"
        assert body["base_saved_at"] is not None
        assert client.get(body["base_url"]).content == b"%PDF-1.4\n%%EOF\n"
        assert body["stale"] is False
        pdf_time = (directory / "paper.pdf").stat().st_mtime
        # Hidden directories are ignored; a newer source marks the PDF stale.
        (directory / ".hidden").mkdir()
        (directory / ".hidden" / "x.tex").write_text("x")
        os.utime(directory / ".hidden" / "x.tex", (pdf_time + 50, pdf_time + 50))
        assert client.get(url).json()["stale"] is False
        os.utime(directory / "main.tex", (pdf_time + 100, pdf_time + 100))
        assert client.get(url).json()["stale"] is True
        (directory / "paper.pdf").unlink()
        missing = client.get(url).json()
        assert missing["target_url"] is None and missing["stale"] is False
        assert missing["base_url"] is not None


async def test_pdf_diff_errors() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        assert client.get("/api/artifacts/missing/pdf-diff").status_code == 404
        card = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": {"artifact_type": "markdown", "title": "n", "body": "b"}},
        )
        if card.status_code == 201:
            assert client.get(f"/api/artifacts/{card.json()['id']}/pdf-diff").status_code == 409


async def test_snapshot_is_served_only_as_a_pdf() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        url = client.get(f"/api/artifacts/{artifact['id']}/pdf-diff").json()["base_url"]
        served = client.get(url)
        assert served.status_code == 200
        assert served.headers["content-type"] == "application/pdf"
        snapshot_path(session_id, artifact["id"]).write_bytes(b"<html>")
        assert client.get(url).status_code >= 400


async def test_deleting_the_artifact_removes_the_snapshot() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        path = snapshot_path(session_id, artifact["id"])
        assert path.is_file()
        assert client.delete(f"/api/agent/{session_id}/artifacts/{artifact['id']}").json() == {"ok": True}
        assert not path.exists()

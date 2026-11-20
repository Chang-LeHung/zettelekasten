"""A LaTeX artifact keeps the PDF it had at its last save for a before/after view."""

import json
import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from latex_helpers import (
    PDF_TWO,
    commit,
    initialize,
    prepared_project,
    project_directory,
    save,
    snapshot_path,
    status,
)

from zett.application.artifacts import pdf_snapshots as service_module
from zett.application.files.object_store import latex_snapshot_key
from zett.infra.persistence.dao import session_storage
from zett.main import app
from zett.schemas import AgentSessionCreate

prepared = prepared_project


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
            json={"content": {"artifact_type": "article", "title": "n", "content": "b"}},
        )
        assert card.status_code == 201, card.text
        refused = client.get(f"/api/artifacts/{card.json()['id']}/pdf-diff")
        assert refused.status_code == 409
        assert refused.json()["detail"] == "Artifact is not a LaTeX PDF"


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


def put_content(client: TestClient, session_id: str, artifact_id: object, content: dict[str, object]):
    return client.put(f"/api/agent/{session_id}/artifacts/{artifact_id}", json={"content": content})


async def test_user_edit_through_put_captures_the_snapshot() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        directory = project_directory(session_id)
        (directory / "paper.pdf").write_bytes(PDF_TWO)
        commit(directory)
        response = put_content(client, session_id, artifact["id"], artifact["content"])
        assert response.status_code == 200, response.text
        assert snapshot_path(session_id, artifact["id"]).read_bytes() == PDF_TWO


async def test_a_failing_snapshot_write_never_fails_the_save(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_arguments: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(service_module.files, "copy_atomically", explode)
    monkeypatch.setattr(service_module.files, "write_commit", explode)
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        assert not snapshot_path(session_id, artifact["id"]).exists()
        body = client.get(f"/api/artifacts/{artifact['id']}/pdf-diff").json()
        assert body["base_url"] is None


async def test_saving_a_non_latex_artifact_touches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(service_module.files, "copy_atomically", lambda *a: calls.append(a))
    monkeypatch.setattr(service_module.files, "write_commit", lambda *a: calls.append(a))
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        card = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": {"artifact_type": "article", "title": "n", "content": "b"}},
        )
        assert card.status_code == 201, card.text
        assert save(client, session_id, card.json()["id"]).status_code == 200
        updated = put_content(
            client, session_id, card.json()["id"], {"artifact_type": "article", "title": "n", "content": "c"}
        )
        assert updated.status_code == 200, updated.text
        assert not snapshot_path(session_id, card.json()["id"]).parent.exists()
    assert calls == []


async def test_staleness_ignores_build_output() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        directory = project_directory(session_id)
        url = f"/api/artifacts/{artifact['id']}/pdf-diff"
        pdf_time = (directory / "paper.pdf").stat().st_mtime
        for name in ("paper.aux", "paper.log", "extra.pdf"):
            (directory / name).write_text("x")
            os.utime(directory / name, (pdf_time + 100, pdf_time + 100))
        assert client.get(url).json()["stale"] is False
        (directory / "extra.bib").write_text("x")
        os.utime(directory / "extra.bib", (pdf_time + 100, pdf_time + 100))
        assert client.get(url).json()["stale"] is True


async def test_changing_the_type_away_from_latex_discards_the_snapshot() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        path = snapshot_path(session_id, artifact["id"])
        assert path.is_file() and path.with_suffix(".json").is_file()
        response = put_content(
            client, session_id, artifact["id"], {"artifact_type": "article", "title": "n", "content": "b"}
        )
        assert response.status_code == 200, response.text
        assert not path.exists() and not path.with_suffix(".json").exists()


async def test_a_truncated_source_pdf_leaves_a_coherent_state() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        directory = project_directory(session_id)
        assert save(client, session_id, artifact["id"]).status_code == 200
        path = snapshot_path(session_id, artifact["id"])
        sidecar = path.with_suffix(".json")
        for broken in (b"%PDF-1.4\nhalf written", b"%PDF-1.4\n" + b"x" * 3000 + b"\n%%EOF\n" + b"y" * 2000):
            assert save(client, session_id, artifact["id"]).status_code == 200
            assert path.is_file()
            before = json.loads(sidecar.read_text())
            (directory / "paper.pdf").write_bytes(broken)
            commit(directory, "docs: broken")
            assert save(client, session_id, artifact["id"]).status_code == 200
            after = json.loads(sidecar.read_text())
            assert not path.exists()
            assert after["commit"] != before["commit"] and after["saved_at"] >= before["saved_at"]
            body = client.get(f"/api/artifacts/{artifact['id']}/pdf-diff").json()
            assert body["base_url"] is None
            (directory / "paper.pdf").write_bytes(PDF_TWO)
            commit(directory, "docs: fixed")
        assert not list(path.parent.glob(".snapshot-*"))


async def test_has_newer_source_reports_true_at_the_scan_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from zett.infra.artifacts import pdf_snapshots as files

    with TestClient(app) as client:
        session_id, _ = await prepared(client)
        directory = project_directory(session_id)
        future = datetime.now(UTC).timestamp() + 1000
        assert files.has_newer_source(directory, future) is False
        monkeypatch.setattr(files, "MAX_SCANNED_FILES", 1)
        assert files.has_newer_source(directory, future) is True


async def test_saved_at_is_recorded_and_independent_of_mtime() -> None:
    with TestClient(app) as client:
        session_id, artifact = await prepared(client)
        before = datetime.now(UTC)
        assert save(client, session_id, artifact["id"]).status_code == 200
        path = snapshot_path(session_id, artifact["id"])
        recorded = datetime.fromisoformat(json.loads(path.with_suffix(".json").read_text())["saved_at"])
        assert recorded >= before
        os.utime(path, (1_000_000, 1_000_000))
        shown = datetime.fromisoformat(client.get(f"/api/artifacts/{artifact['id']}/pdf-diff").json()["base_saved_at"])
        assert shown == recorded
        # An older snapshot without a sidecar falls back to the file's mtime.
        path.with_suffix(".json").unlink()
        shown = datetime.fromisoformat(client.get(f"/api/artifacts/{artifact['id']}/pdf-diff").json()["base_saved_at"])
        assert shown == datetime.fromtimestamp(1_000_000, tz=UTC)


async def test_sidecar_is_written_without_a_pdf_or_git() -> None:
    with TestClient(app) as client:
        session_id = (await session_storage.create(AgentSessionCreate())).session_id
        artifact = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": {"artifact_type": "latex_pdf", "pdf_name": "paper.pdf"}},
        ).json()
        project_directory(session_id).joinpath("main.tex").write_text("x")
        # Not a repository: the save is refused, so only a committed project reaches the sidecar.
        assert save(client, session_id, artifact["id"]).status_code == 409
        directory = project_directory(session_id)
        initialize(directory)
        assert save(client, session_id, artifact["id"]).status_code == 200
        sidecar = snapshot_path(session_id, artifact["id"]).with_suffix(".json")
        data = json.loads(sidecar.read_text())
        assert data["commit"] and data["saved_at"]
        assert not snapshot_path(session_id, artifact["id"]).exists()

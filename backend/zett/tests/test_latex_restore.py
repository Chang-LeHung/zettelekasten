"""The user can discard everything the Agent changed since the last save, keeping history."""

import json
import subprocess

from fastapi.testclient import TestClient
from latex_helpers import (
    PDF_TWO,
    commit,
    git,
    git_result,
    prepared_project,
    project_directory,
    save,
    snapshot_path,
    status,
    subjects,
)

from zett.infra.artifacts import git_projects
from zett.infra.persistence.dao import session_storage
from zett.main import app
from zett.schemas import AgentSessionCreate


async def prepared(client: TestClient):
    session_id, artifact = await prepared_project(client)
    return session_id, artifact, project_directory(session_id)


def agent_edit(directory, text: str = "changed", message: str = "docs: edit") -> None:
    (directory / "main.tex").write_text(text)
    commit(directory, message)


def restore_url(session_id: str, artifact) -> str:
    return f"/api/agent/{session_id}/artifacts/{artifact['id']}/restore"


def diff(client: TestClient, artifact) -> dict:
    return client.get(f"/api/artifacts/{artifact['id']}/pdf-diff").json()


async def test_save_records_commit_and_counts_later_commits() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert diff(client, artifact)["commits_since"] is None
        assert diff(client, artifact)["can_restore"] is False
        assert save(client, session_id, artifact["id"]).status_code == 200
        sidecar = snapshot_path(session_id, artifact["id"]).with_suffix(".json")
        assert json.loads(sidecar.read_text())["commit"] == git(directory, "rev-parse", "HEAD").strip()
        assert diff(client, artifact)["commits_since"] == 0
        assert diff(client, artifact)["can_restore"] is False
        agent_edit(directory, "one")
        agent_edit(directory, "two")
        body = diff(client, artifact)
        assert body["commits_since"] == 2 and body["can_restore"] is True
        client.delete(f"/api/agent/{session_id}/artifacts/{artifact['id']}")
        assert not sidecar.exists()


async def test_restore_reverts_and_keeps_history() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        original = (directory / "main.tex").read_text()
        assert save(client, session_id, artifact["id"]).status_code == 200
        agent_edit(directory, "one", "docs: one")
        agent_edit(directory, "two", "docs: two")
        response = client.post(restore_url(session_id, artifact))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["restored_commits"] == 2
        assert body["commits_since"] == 0 and body["can_restore"] is False
        assert (directory / "main.tex").read_text() == original
        assert subjects(directory)[0] == "revert: restore the version saved by the user"
        assert subjects(directory)[1:3] == ["docs: two", "docs: one"]
        assert status(directory) == ""
        assert client.post(restore_url(session_id, artifact)).status_code == 409


async def test_restore_copies_the_snapshot_pdf_back() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        (directory / "paper.pdf").write_bytes(PDF_TWO)
        agent_edit(directory)
        assert (directory / "paper.pdf").read_bytes() == PDF_TWO
        assert client.post(restore_url(session_id, artifact)).status_code == 200
        assert (directory / "paper.pdf").read_bytes() == b"%PDF-1.4\n%%EOF\n"
        assert status(directory) == ""


async def test_restore_amends_a_tracked_pdf_that_differs() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert "paper.pdf" in git(directory, "ls-files")
        assert save(client, session_id, artifact["id"]).status_code == 200
        snapshot_path(session_id, artifact["id"]).write_bytes(PDF_TWO)
        agent_edit(directory)
        before = len(subjects(directory))
        assert client.post(restore_url(session_id, artifact)).status_code == 200
        assert (directory / "paper.pdf").read_bytes() == PDF_TWO
        assert status(directory) == ""
        assert len(subjects(directory)) == before + 1


async def test_restore_refusals() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        url = restore_url(session_id, artifact)
        assert client.post(f"/api/agent/{session_id}/artifacts/missing/restore").status_code == 404
        agent_edit(directory)
        unsaved = client.post(url)
        assert unsaved.status_code == 409 and "save" in unsaved.json()["detail"]
        assert save(client, session_id, artifact["id"]).status_code == 200
        agent_edit(directory, "later")
        (directory / "dirty.tex").write_text("x")
        dirty = client.post(url)
        assert dirty.status_code == 409 and "uncommitted" in dirty.json()["detail"]
        (directory / "dirty.tex").unlink()
        # Rewriting history so the saved commit is gone.
        git(directory, "reset", "--hard", "HEAD~2")
        agent_edit(directory, "other", "docs: other")
        gone = client.post(url)
        assert gone.status_code == 409 and "history" in gone.json()["detail"]


async def test_restore_refuses_a_merge_in_the_range() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        git(directory, "checkout", "-q", "-b", "side")
        (directory / "side.tex").write_text("s")
        commit(directory, "docs: side")
        git(directory, "checkout", "-q", "main")
        agent_edit(directory, "main change")
        git(
            directory,
            "-c",
            "user.name=A",
            "-c",
            "user.email=a@example.com",
            "merge",
            "-q",
            "--no-ff",
            "side",
            "-m",
            "m",
        )
        refused = client.post(restore_url(session_id, artifact))
        assert refused.status_code == 409 and "merge" in refused.json()["detail"]


async def test_restore_refuses_non_latex() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        card = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": {"artifact_type": "article", "title": "n", "content": "b"}},
        )
        assert card.status_code == 201, card.text
        assert client.post(f"/api/agent/{session_id}/artifacts/{card.json()['id']}/restore").status_code == 409


async def test_restore_of_another_sessions_artifact_is_404() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        agent_edit(directory)
        other = (await session_storage.create(AgentSessionCreate())).session_id
        head = git(directory, "rev-parse", "HEAD")
        assert client.post(restore_url(other, artifact)).status_code == 404
        assert git(directory, "rev-parse", "HEAD") == head


async def test_restore_keeps_the_original_saved_at() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        sidecar = snapshot_path(session_id, artifact["id"]).with_suffix(".json")
        data = json.loads(sidecar.read_text())
        agent_edit(directory)
        assert client.post(restore_url(session_id, artifact)).status_code == 200
        after = json.loads(sidecar.read_text())
        assert after["saved_at"] == data["saved_at"]
        assert after["commit"] == git(directory, "rev-parse", "HEAD").strip() != data["commit"]


async def test_restore_works_without_a_snapshot_pdf() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        snapshot_path(session_id, artifact["id"]).unlink()
        agent_edit(directory)
        response = client.post(restore_url(session_id, artifact))
        assert response.status_code == 200, response.text
        assert response.json()["base_url"] is None
        assert status(directory) == ""


async def test_a_commit_landing_inside_the_window_is_not_reverted(monkeypatch) -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        agent_edit(directory, "one", "docs: one")
        real = git_projects.commits_between
        landed = []

        def counting(directory_, base, head="HEAD"):
            count = real(directory_, base, head)
            if not landed:
                landed.append(True)
                (directory_ / "late.tex").write_text("late")
                commit(directory_, "docs: late")
            return count

        monkeypatch.setattr(git_projects, "commits_between", counting)
        response = client.post(restore_url(session_id, artifact))
        assert response.status_code == 200, response.text
        assert response.json()["restored_commits"] == 1
        assert (directory / "late.tex").read_text() == "late"
        assert status(directory) == ""


def partial_revert_stub(monkeypatch, directory, swallow_abort: bool):
    real = git_projects._git
    seen = {}

    def stub(path, *arguments, check=True):
        if arguments[:2] == ("revert", "--no-commit"):
            real(path, *arguments, check=check)
            # A real, half-applied revert is now on disk.
            seen["dirty"] = status(directory) != ""
            return subprocess.CompletedProcess(arguments, 1, "", "CONFLICT")
        if swallow_abort and arguments[:2] == ("revert", "--abort"):
            return subprocess.CompletedProcess(arguments, 0, "", "")
        return real(path, *arguments, check=check)

    monkeypatch.setattr(git_projects, "_git", stub)
    return seen


async def check_partial_revert(monkeypatch, swallow_abort: bool) -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert save(client, session_id, artifact["id"]).status_code == 200
        agent_edit(directory, "a", "docs: a")
        agent_edit(directory, "later", "docs: b")
        seen = partial_revert_stub(monkeypatch, directory, swallow_abort)
        head = git(directory, "rev-parse", "HEAD")
        response = client.post(restore_url(session_id, artifact))
        assert response.status_code == 409, response.text
        assert "automatically" in response.json()["detail"]
        # Without the recovery the half-applied revert would still be there.
        assert seen["dirty"] is True
        assert status(directory) == ""
        assert git(directory, "rev-parse", "HEAD") == head
        assert (directory / "main.tex").read_text() == "later"
        assert git_result(directory, "rev-parse", "-q", "--verify", "REVERT_HEAD").returncode != 0


async def test_failing_revert_aborts_and_leaves_a_clean_tree(monkeypatch) -> None:
    await check_partial_revert(monkeypatch, swallow_abort=False)


async def test_a_useless_abort_falls_back_to_a_hard_reset(monkeypatch) -> None:
    await check_partial_revert(monkeypatch, swallow_abort=True)


async def test_amend_is_skipped_when_head_moved() -> None:
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        stale = git(directory, "rev-parse", "HEAD").strip()
        (directory / "late.tex").write_text("late")
        commit(directory, "docs: late")
        (directory / "paper.pdf").write_bytes(PDF_TWO)
        before = subjects(directory)
        assert git_projects.amend_with_path(directory, "paper.pdf", stale) is False
        assert subjects(directory) == before
        assert git_projects.amend_with_path(directory, "paper.pdf", git(directory, "rev-parse", "HEAD").strip())


async def test_restore_falls_back_to_an_identity_when_none_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    for key in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as client:
        session_id, artifact, directory = await prepared(client)
        assert git_result(directory, "config", "user.name").stdout.strip() == ""
        assert save(client, session_id, artifact["id"]).status_code == 200
        agent_edit(directory)
        response = client.post(restore_url(session_id, artifact))
        assert response.status_code == 200, response.text
        assert git(directory, "log", "-1", "--pretty=%an <%ae>").strip() == "Zett Restore <restore@zett.local>"

"""The Agent owns a LaTeX project's git history; Zett verifies it before publishing."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from latex_helpers import (
    AGENT_IDENTITY,
    commit,
    create_pdf_artifact,
    git,
    initialize,
    project_directory,
    save,
    status,
    subjects,
    write_sources,
)

from zett.application.artifacts import versioning as versioning_module
from zett.config import settings
from zett.infra.artifacts import git_projects
from zett.infra.artifacts.git_projects import GitProjectError
from zett.infra.persistence.dao import session_storage
from zett.main import app
from zett.schemas import AgentSessionCreate


async def test_creating_an_artifact_touches_no_git() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        create_pdf_artifact(client, session_id)
    directory = project_directory(session_id)
    assert directory.is_dir()
    # Zett only allocates the directory; the repository is entirely the Agent's work.
    assert list(directory.iterdir()) == []
    assert not (directory / ".git").exists()
    assert not (directory / ".gitignore").exists()


async def test_save_refuses_a_project_that_is_not_a_repository() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        write_sources(project_directory(session_id))
        refused = save(client, session_id, artifact["id"])
        assert refused.status_code == 409, refused.text
        assert "not a git repository" in refused.json()["detail"]
        # A refused save must not publish the draft.
        stored = client.get(f"/api/agent/{session_id}/artifacts/{artifact['id']}").json()
        assert stored["status"] == "draft"


async def test_save_refuses_a_project_with_uncommitted_changes() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        directory = project_directory(session_id)
        initialize(directory)
        assert save(client, session_id, artifact["id"]).status_code == 200
        (directory / "intro.tex").write_text("new section")
        refused = save(client, session_id, artifact["id"])
        assert refused.status_code == 409, refused.text
        assert "intro.tex" in refused.json()["detail"]


async def test_save_publishes_a_committed_project_without_committing_itself() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        directory = project_directory(session_id)
        write_sources(directory)
        initialize(directory, "docs(paper): add introduction")
        # A compiled project stays clean because the Agent's own .gitignore covers the build files.
        assert status(directory) == ""
        assert subjects(directory) == ["docs(paper): add introduction"]
        saved = save(client, session_id, artifact["id"])
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "saved"
    # Publishing adds no commit and needs none.
    assert subjects(directory) == ["docs(paper): add introduction"]
    assert status(directory) == ""


async def test_publish_through_the_library_editor_checks_the_same_tree() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        directory = project_directory(session_id)
        write_sources(directory)
        initialize(directory)
        published = {
            "artifact_type": "latex_pdf",
            "pdf_name": "paper.pdf",
            "project_path": artifact["content"]["project_path"],
        }
        endpoint = f"/api/agent/{session_id}/artifacts/{artifact['id']}"
        assert client.put(endpoint, json={"content": published}).status_code == 200
        (directory / "extra.tex").write_text("extra")
        refused = client.put(endpoint, json={"content": published})
        assert refused.status_code == 409, refused.text
        commit(directory)
        assert client.put(endpoint, json={"content": published}).status_code == 200


async def test_verification_covers_only_the_project_subtree(tmp_path: Path) -> None:
    """Other work in a user repository must never block a save."""
    git(tmp_path, "init", "-q", "-b", "main", ".")
    (tmp_path / "unrelated.txt").write_text("user work")
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        directory = project_directory(session_id)
        # Zett does not create a repository, and it does not nest one inside the user's.
        assert not (directory / ".git").exists()
        write_sources(directory)
        git(tmp_path, "add", "-A", "--", f"artifacts/{session_id}/paper")
        git(tmp_path, *AGENT_IDENTITY, "commit", "-q", "-m", "docs(paper): add introduction")
        assert status(directory) == ""
        assert save(client, session_id, artifact["id"]).status_code == 200
        assert git(tmp_path, "status", "--porcelain", "--", "unrelated.txt").strip() == "?? unrelated.txt"
        tracked = git(tmp_path, "ls-files", f"artifacts/{session_id}/paper").split()
        assert f"artifacts/{session_id}/paper/main.tex" in tracked


async def test_missing_project_directory_is_not_verified() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        shutil.rmtree(project_directory(session_id))
        # There is no working tree left to publish from, so metadata still saves.
        assert save(client, session_id, artifact["id"]).status_code == 200


async def test_non_pdf_artifacts_are_never_verified() -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        created = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": {"artifact_type": "card", "title": "One idea", "content": "Body"}},
        )
        assert created.status_code == 201, created.text
        assert save(client, session_id, created.json()["id"]).status_code == 200
    assert not (settings.storage_root / "artifacts").exists()


async def test_unusable_git_never_blocks_a_save(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = (await session_storage.create(AgentSessionCreate())).session_id
    with TestClient(app) as client:
        artifact = create_pdf_artifact(client, session_id)
        write_sources(project_directory(session_id))

        def unavailable(*_arguments: object) -> object:
            raise GitProjectError("git is not installed")

        # A git Zett cannot run says nothing about the project, so the save still succeeds.
        monkeypatch.setattr(versioning_module, "is_repository", unavailable)
        assert save(client, session_id, artifact["id"]).status_code == 200


def test_git_environment_drops_redirecting_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """An enclosing git process must not redirect the project repository.

    Windows environment names are case-insensitive, so a lowercase override has
    to be dropped as well.
    """
    monkeypatch.setenv("git_dir", "/tmp/elsewhere")
    monkeypatch.setenv("GIT_WORK_TREE", "/tmp/elsewhere")
    environment = git_projects._environment()
    assert {key.upper() for key in environment}.isdisjoint({"GIT_DIR", "GIT_WORK_TREE"})
    assert environment["GIT_TERMINAL_PROMPT"] == "0"

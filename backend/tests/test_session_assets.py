import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zett import config
from zett.application.services import KnowledgeWorkspaceApplicationService, SessionAssetApplicationService
from zett.domain.services import DomainError
from zett.infra.agent_session_dao import agent_session_storage
from zett.infra.session_asset_dao import session_asset_storage
from zett.main import app
from zett.schemas import AgentSessionCreate, SessionLinkAssetIn, SessionTextAssetIn


def test_session_assets_store_typed_metadata_and_binary_files() -> None:
    session = agent_session_storage.create(AgentSessionCreate(title="Assets"))

    text_asset = SessionAssetApplicationService.create_text(
        session.id,
        SessionTextAssetIn(name="Notes", content="A local note."),
    )
    link_asset = SessionAssetApplicationService.create_link(
        session.id,
        SessionLinkAssetIn(name="Reference", url="https://example.com/reference"),
    )
    image_asset = SessionAssetApplicationService.create_binary(
        session.id,
        "../diagram.png",
        "image/png",
        b"fake-png-content",
    )

    session_directory = config.settings.asset_directory / session.id
    stored_files = list(session_directory.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].parent == session_directory
    assert stored_files[0].name.startswith(image_asset.id)
    assert stored_files[0].read_bytes() == b"fake-png-content"
    assert text_asset.text_content == "A local note."
    assert link_asset.source_url == "https://example.com/reference"
    assert image_asset.asset_type == "image"
    assert image_asset.content_url == f"/api/agent/{session.id}/assets/{image_asset.id}/content"

    restored = KnowledgeWorkspaceApplicationService.get_session(session.id)
    assert restored is not None
    assert [asset.id for asset in restored.assets] == [text_asset.id, link_asset.id, image_asset.id]


def test_session_asset_access_is_scoped_and_session_delete_removes_directory() -> None:
    first = agent_session_storage.create(AgentSessionCreate(title="First"))
    second = agent_session_storage.create(AgentSessionCreate(title="Second"))
    asset = SessionAssetApplicationService.create_binary(first.id, "data.bin", "application/octet-stream", b"data")
    stored_path = session_asset_storage.content_path(first.id, asset.id)
    assert isinstance(stored_path, Path)
    assert session_asset_storage.get_for_session(second.id, asset.id) is None
    assert session_asset_storage.content_path(second.id, asset.id) is None

    result = KnowledgeWorkspaceApplicationService.delete_session(first.id)

    assert result == {"ok": True}
    assert not (config.settings.asset_directory / first.id).exists()
    assert session_asset_storage.get(asset.id) is None


def test_asset_validation_rejects_invalid_links_and_large_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    with pytest.raises(DomainError, match="absolute HTTP or HTTPS"):
        SessionAssetApplicationService.create_link(
            session.id,
            SessionLinkAssetIn(name="Unsafe", url="file:///tmp/private.txt"),
        )

    monkeypatch.setattr(config.settings, "max_asset_size_bytes", 3)
    with pytest.raises(ValueError, match="upload limit"):
        SessionAssetApplicationService.create_binary(session.id, "large.bin", "application/octet-stream", b"1234")

    config.settings.asset_directory.mkdir(parents=True)
    marker = config.settings.asset_directory / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(ValueError, match="canonical UUID"):
        session_asset_storage.delete_session("..")
    assert marker.read_text() == "keep"


def test_session_asset_http_api_serves_uploaded_content() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    with TestClient(app) as client:
        response = client.post(
            f"/api/agent/{session.id}/assets/upload",
            params={"name": "example.png"},
            content=b"image-content",
            headers={"Content-Type": "image/png"},
        )
        assert response.status_code == 200
        asset = response.json()
        assert asset["asset_type"] == "image"

        listing = client.get(f"/api/agent/{session.id}/assets")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()] == [asset["id"]]

        content = client.get(asset["content_url"])
        assert content.status_code == 200
        assert content.headers["content-type"] == "image/png"
        assert content.content == b"image-content"


def test_agent_workspace_manifest_projects_registered_session_assets() -> None:
    session = agent_session_storage.create(AgentSessionCreate(title="Agent filesystem"))
    note = SessionAssetApplicationService.create_text(
        session.id,
        SessionTextAssetIn(name="Context", content="Only this session can read me."),
    )
    link = SessionAssetApplicationService.create_link(
        session.id,
        SessionLinkAssetIn(name="Reference", url="https://example.com/reference"),
    )
    binary = SessionAssetApplicationService.create_binary(
        session.id,
        "diagram.png",
        "image/png",
        b"image-content",
    )

    workspace = session_asset_storage.prepare_agent_workspace(session.id)
    manifest = json.loads((workspace / ".zett-assets.json").read_text(encoding="utf-8"))
    entries = {item["id"]: item for item in manifest["assets"]}

    assert workspace == config.settings.asset_directory / session.id
    assert entries[note.id]["content"] == "Only this session can read me."
    assert entries[link.id]["content"] == "https://example.com/reference"
    assert entries[binary.id]["file_path"].startswith("/")
    assert str(config.settings.asset_directory) not in json.dumps(manifest)

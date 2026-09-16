"""Real isolated SQLite tests for the new storage-only foundation."""

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from zett_agent import UserMessage

from zett.config import settings
from zett.infra.agent_runtime import get_agent_runtime_storage
from zett.infra.dao.artifact import artifact_storage
from zett.infra.dao.asset import session_asset_storage
from zett.infra.dao.session import session_storage
from zett.infra.models import Base
from zett.infra.storage import AsyncStorage, Storage
from zett.main import app
from zett.models import ArtifactListOptions, SessionAssetListOptions, SessionListOptions
from zett.schemas import AgentArtifactWrite, AgentSessionCreate, CardArtifactContent, SessionAssetCreate


async def test_sessions_reuse_agent_storage_and_paginate_raw_history():
    assert isinstance(session_storage, AsyncStorage)
    first = await session_storage.create(AgentSessionCreate(title="First"))
    second = await session_storage.create(AgentSessionCreate(title="Second"))
    assert UUID(first.session_id).version == 7
    fetched = await session_storage.get(first.session_id)
    assert fetched is not None and fetched.title == "First"
    renamed = await session_storage.update(first.session_id, AgentSessionCreate(title="Renamed"))
    assert renamed.title == "Renamed"
    assert len(await session_storage.list(SessionListOptions(limit=1, offset=1))) == 1
    assert await session_storage.list(SessionListOptions(offset=100)) == []
    runtime = get_agent_runtime_storage()
    await runtime.append(first.session_id, "request-1", UserMessage(content="one"))
    await runtime.append(first.session_id, "request-2", UserMessage(content="two"))
    page = await session_storage.list_raw_messages(first.session_id, limit=1, offset=1)
    assert page[0].message.text == "two"
    assert await session_storage.list_raw_messages(second.session_id) == []
    with pytest.raises(KeyError):
        await session_storage.update("missing", AgentSessionCreate(title="Title"))


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("text", {"text_content": "Notes"}),
        ("link", {"source_url": "https://example.com"}),
        ("image", {"content": b"image"}),
        ("file", {"content": b"file"}),
    ],
)
async def test_asset_crud_is_typed_and_session_scoped(kind, payload):
    assert isinstance(session_asset_storage, Storage)
    owner = (await session_storage.create(AgentSessionCreate())).session_id
    other = (await session_storage.create(AgentSessionCreate())).session_id
    entity = SessionAssetCreate(session_id=owner, asset_type=kind, name="../asset.bin", **payload)
    asset = await session_asset_storage.create(entity)
    assert UUID(asset.id).version == 7
    assert session_asset_storage.get_for_session(other, asset.id) is None
    assert session_asset_storage.content_path(other, asset.id) is None
    assert session_asset_storage.list(SessionAssetListOptions(session_id=other)) == []
    path = session_asset_storage.content_path(owner, asset.id)
    if kind in {"file", "image"}:
        assert path.parent == settings.asset_directory / owner
        assert path.read_bytes() == payload["content"]
    updated = session_asset_storage.update(asset.id, entity.model_copy(update={"name": "Renamed"}))
    assert updated.id == asset.id and updated.name == "Renamed"
    if path is not None:
        assert not path.exists()
        assert session_asset_storage.content_path(owner, asset.id).read_bytes() == payload["content"]
    with pytest.raises(KeyError):
        session_asset_storage.update(asset.id, entity.model_copy(update={"session_id": other}))
    assert session_asset_storage.delete(asset.id)
    assert not session_asset_storage.delete(asset.id)


async def test_session_deletion_explicitly_cleans_owned_assets_and_artifacts():
    owner = (await session_storage.create(AgentSessionCreate())).session_id
    other = (await session_storage.create(AgentSessionCreate())).session_id
    for sid in (owner, other):
        await session_asset_storage.create(
            SessionAssetCreate(session_id=sid, asset_type="file", name="f", content=b"x")
        )
        await artifact_storage.create(
            AgentArtifactWrite(session_id=sid, content=CardArtifactContent(title="Card", content="Body"))
        )
    assert await session_storage.delete(owner)
    assert not await session_storage.delete(owner)
    assert await session_storage.get(owner) is None
    assert not (settings.asset_directory / owner).exists()
    assert artifact_storage.list(ArtifactListOptions(session_id=owner)) == []
    assert session_asset_storage.list(SessionAssetListOptions(session_id=owner)) == []
    assert len(artifact_storage.list(ArtifactListOptions(session_id=other))) == 1
    assert (settings.asset_directory / other).is_dir()


@pytest.mark.parametrize("kind", ["text", "link", "file", "image"])
async def test_missing_asset_payload_does_not_mutate_storage(kind):
    owner = (await session_storage.create(AgentSessionCreate())).session_id
    with pytest.raises(ValueError):
        await session_asset_storage.create(SessionAssetCreate(session_id=owner, asset_type=kind, name="Empty"))
    assert session_asset_storage.list() == []
    assert not (settings.asset_directory / owner).exists()


def test_schema_and_http_surface_contain_no_retired_business_logic(isolated_database):
    expected_tables = {
        "artifact_tags",
        "key_values",
        "providers",
        "session_artifacts",
        "session_assets",
        "tags",
    }
    assert set(Base.metadata.tables) == expected_tables
    assert set(inspect(isolated_database).get_table_names()) == expected_tables
    assert all(not column.foreign_keys for table in Base.metadata.tables.values() for column in table.columns)
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"ok": True}
        paths = set(client.get("/openapi.json").json()["paths"])
        assert "/api/agent/sessions" in paths
        assert "/api/agent/{session_id}/assets" in paths
        assert "/api/agent/{session_id}/artifacts" in paths
        assert "/api/ai/providers" in paths
        assert "/api/artifacts" in paths
        assert "/api/library/tags" in paths
        assert "/api/settings" in paths
        for path in ("/api/cards", "/api/tags", "/api/library", "/api/ai/providers"):
            expected = 200 if path == "/api/ai/providers" else 404
            assert client.get(path).status_code == expected
        from zett import main

        if Path(main.static_directory, "index.html").is_file():
            response = client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

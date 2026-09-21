"""Storage and HTTP lifecycle tests for session-independent static assets."""

from uuid import UUID

from fastapi.testclient import TestClient

from zett.config import settings
from zett.infra.dao import static_asset_storage
from zett.infra.files.object_store import get_object_store
from zett.main import app
from zett.schemas import StaticAssetCreate, StaticAssetListOptions


async def test_static_asset_storage_updates_files_and_removes_owned_content():
    created = await static_asset_storage.create(
        StaticAssetCreate(name="reference.txt", mime_type="text/plain", content=b"first")
    )

    assert UUID(created.id).version == 7
    assert created.storage_path == f"assets/static/{created.id}.txt"
    assert created.content_url == f"/api/files/{created.storage_path}"
    first_path = await static_asset_storage.content_path(created.id)
    assert first_path is not None
    assert first_path.parent == settings.storage_root / "assets" / "static"
    assert first_path.read_bytes() == b"first"
    assert [asset.id for asset in await static_asset_storage.list(StaticAssetListOptions(query="reference"))] == [
        created.id
    ]

    updated = await static_asset_storage.update(
        created.id,
        StaticAssetCreate(name="renamed.bin", mime_type="application/octet-stream", content=b"second"),
    )
    replacement_path = await static_asset_storage.content_path(created.id)
    assert replacement_path is not None
    assert replacement_path.read_bytes() == b"second"
    assert not first_path.exists()
    assert updated.name == "renamed.bin"

    assert await static_asset_storage.delete(created.id) is True
    assert not replacement_path.exists()
    assert await static_asset_storage.get(created.id) is None
    assert not await static_asset_storage.delete(created.id)


def test_static_asset_http_lifecycle_uses_runtime_upload_limit():
    with TestClient(app) as client:
        assert client.get("/api/assets").json() == []
        assert client.put("/api/settings", json={"max_asset_size_bytes": 3}).status_code == 200

        oversized = client.post(
            "/api/assets/upload?name=large.bin",
            content=b"1234",
            headers={"content-type": "application/octet-stream"},
        )
        assert oversized.status_code == 413

        uploaded = client.post(
            "/api/assets/upload?name=image.png",
            content=b"png",
            headers={"content-type": "image/png"},
        )
        assert uploaded.status_code == 201
        asset = uploaded.json()
        assert asset["content_url"].startswith("/api/files/assets/static/")
        listed = client.get("/api/assets").json()
        assert len(listed) == 1
        assert listed[0]["id"] == asset["id"]
        assert listed[0]["name"] == "image.png"

        content = client.get(asset["content_url"])
        assert content.status_code == 200
        assert content.content == b"png"
        assert content.headers["content-disposition"].startswith("inline;")
        assert content.headers["x-content-type-options"] == "nosniff"

        assert client.delete(f"/api/assets/{asset['id']}").json() == {"ok": True}
        assert client.get("/api/assets").json() == []


def test_importing_static_asset_into_session_keeps_object_reference_without_copying_file():
    with TestClient(app) as client:
        owner = client.post("/api/agent/start").json()["conversation_id"]
        static_asset = client.post(
            "/api/assets/upload?name=reference.png",
            content=b"png",
            headers={"content-type": "image/png"},
        ).json()

        imported = client.post(
            f"/api/agent/{owner}/assets/import/static/{static_asset['id']}",
        )

        assert imported.status_code == 201
        asset = imported.json()
        assert asset["asset_type"] == "link"
        assert asset["name"] == "reference.png"
        assert asset["mime_type"] == "image/png"
        assert asset["source_url"] is None
        assert asset["source_path"] == static_asset["storage_path"]
        assert asset["content_url"] == static_asset["content_url"]
        assert asset["metadata"] == {
            "import_mode": "object",
            "static_asset_id": static_asset["id"],
            "static_asset_size_bytes": 3,
            "static_asset_sha256": static_asset["sha256"],
        }
        assert get_object_store().resolve(asset["source_path"]).read_bytes() == b"png"
        assert client.get(static_asset["content_url"]).content == b"png"

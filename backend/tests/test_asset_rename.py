"""Names are editable metadata, not binary storage keys or public identities."""

from fastapi.testclient import TestClient

from zett.infra.dao import session_asset_storage
from zett.main import app


def test_rename_preserves_file_and_reference_and_checks_ownership():
    with TestClient(app) as client:
        owner = client.post("/api/agent/start").json()["conversation_id"]
        other = client.post("/api/agent/start").json()["conversation_id"]
        original = client.post(
            f"/api/agent/{owner}/assets/upload?name=upload.png",
            content=b"image-bytes",
            headers={"content-type": "image/png"},
        ).json()
        asset_id = original["id"]
        original = client.get(f"/api/agent/{owner}/assets/{asset_id}").json()
        path = session_asset_storage.content_path(owner, asset_id)
        assert path is not None
        before = path.stat().st_mtime_ns
        route = f"/api/agent/{owner}/assets/{asset_id}/name"
        assert client.patch(f"/api/agent/{other}/assets/{asset_id}/name", json={"name": "wrong"}).status_code == 404
        for name in ["", "   ", "x" * 501, "bad\x00name"]:
            assert client.patch(route, json={"name": name}).status_code == 422
        response = client.patch(route, json={"name": "  南京大学校徽  "})
        assert response.status_code == 200
        updated = response.json()
        assert updated["name"] == "南京大学校徽"
        for key in ["id", "session_id", "content_url", "sha256", "size_bytes", "mime_type", "created_at"]:
            assert updated[key] == original[key]
        assert session_asset_storage.content_path(owner, asset_id) == path
        assert path.read_bytes() == b"image-bytes"
        assert path.stat().st_mtime_ns == before
        assert client.get(original["content_url"]).content == b"image-bytes"
        assert client.get(f"/api/agent/{owner}/assets").json()[0]["name"] == "南京大学校徽"


def test_text_and_link_names_preserve_payloads():
    with TestClient(app) as client:
        owner = client.post("/api/agent/start").json()["conversation_id"]
        for kind, payload, field in [
            ("text", {"name": "Note", "content": "Keep this"}, "text_content"),
            ("link", {"name": "Site", "url": "https://example.com"}, "source_url"),
        ]:
            original = client.post(f"/api/agent/{owner}/assets/{kind}", json=payload).json()
            response = client.patch(f"/api/agent/{owner}/assets/{original['id']}/name", json={"name": "Reference"})
            assert response.status_code == 200
            assert response.json()[field] == original[field]

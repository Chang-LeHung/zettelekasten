"""Existing Artifact routes support external clients without new resource routes."""

from fastapi.testclient import TestClient

from zett.main import app


def _saved_card(title: str, body: str) -> dict[str, object]:
    return {
        "content": {"artifact_type": "card", "title": title, "content": body},
        "status": "saved",
        "metadata": {"source": "test-suite"},
    }


def test_published_search_does_not_match_unpublished_or_raw_text() -> None:
    with TestClient(app) as client:
        published = client.post("/api/artifacts", json=_saved_card("Published", "Reusable conclusion")).json()
        draft = client.post("/api/artifacts", json={**_saved_card("Draft", "Hidden idea"), "status": "draft"}).json()
        client.post("/api/artifacts", json={**_saved_card("Clean", "Public"), "raw_content": "Secret source"})
        client.put(
            f"/api/agent/{published['session_id']}/artifacts/{published['id']}/draft",
            json={"content": {"artifact_type": "card", "title": "Unpublished", "content": "Draft-only insight"}},
        )
        params = {"statuses": "saved", "published_only": "true", "artifact_types": "card"}
        found = client.get("/api/artifacts", params={**params, "q": "Reusable conclusion"})
        assert [item["id"] for item in found.json()] == [published["id"]]
        for hidden in ("Draft-only", "Unpublished", "Secret source", "Hidden idea"):
            assert client.get("/api/artifacts", params={**params, "q": hidden}).json() == []
        assert client.get("/api/artifacts", params={"published_only": "true", "q": "Hidden idea"}).json() == []
        # The existing list endpoint is unchanged for its ordinary web consumers.
        assert client.get("/api/artifacts", params={"q": "Hidden idea"}).json()[0]["id"] == draft["id"]


def test_existing_edit_route_accepts_optional_version_and_refuses_stale_writes() -> None:
    with TestClient(app) as client:
        artifact = client.post("/api/artifacts", json=_saved_card("Original", "Body")).json()
        path = f"/api/agent/{artifact['session_id']}/artifacts/{artifact['id']}"
        content = {"artifact_type": "card", "title": "Updated", "content": "Better"}
        first = client.put(path, json={"content": content, "expected_version": artifact["version"]})
        assert first.status_code == 200, first.text
        assert first.json()["version"] == artifact["version"] + 1
        assert client.put(path, json={"content": content, "expected_version": artifact["version"]}).status_code == 409
        assert client.get(f"/api/artifacts/{artifact['id']}").json()["content"]["content"] == "Better"

        # Existing callers still work without the optional version field.
        assert client.put(path, json={"content": {**content, "title": "Web editor"}}).status_code == 200


def test_versioned_edit_cannot_publish_an_unreviewed_draft() -> None:
    with TestClient(app) as client:
        artifact = client.post("/api/artifacts", json=_saved_card("Original", "Body")).json()
        session_id, artifact_id = artifact["session_id"], artifact["id"]
        path = f"/api/agent/{session_id}/artifacts/{artifact_id}"
        draft = client.put(
            f"{path}/draft",
            json={"content": {"artifact_type": "card", "title": "Draft", "content": "Unpublished"}},
        ).json()
        refused = client.put(
            path,
            json={
                "expected_version": draft["version"],
                "content": {"artifact_type": "card", "title": "External", "content": "Must not publish"},
            },
        )
        assert refused.status_code == 409
        stored = client.get(f"/api/artifacts/{artifact_id}").json()
        assert stored["content"]["content"] == "Body"
        assert stored["draft_content"]["content"] == "Unpublished"

"""Artifacts created without a conversation, through the library session."""

from fastapi.testclient import TestClient

from zett.application.artifacts.library import (
    LIBRARY_SESSION_KEY,
    LIBRARY_SESSION_TITLE,
    LibrarySessionService,
)
from zett.infra.persistence.dao import key_value_storage, session_storage
from zett.main import app
from zett.schemas import SESSION_TYPE_TO_CODE, SessionType


def _card_payload(title: str) -> dict[str, object]:
    return {
        "content": {
            "artifact_type": "card",
            "title": title,
            "content": "A card created without a conversation.",
        },
        "status": "saved",
        "metadata": {"source": "test-suite"},
    }


def test_library_artifacts_share_one_hidden_session() -> None:
    with TestClient(app) as client:
        first = client.post("/api/artifacts", json=_card_payload("First card"))
        second = client.post("/api/artifacts", json=_card_payload("Second card"))

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["session_id"] == second.json()["session_id"]
        owner = first.json()["session_id"]
        # Provenance survives the round trip: the library session has no
        # conversation to attribute the artifact to, so it records `source`.
        assert first.json()["metadata"]["source"] == "test-suite"

        # The conversation sidebar asks for normal sessions only, so the owner
        # never shows up as a chat.
        sidebar = client.get("/api/agent/sessions", params={"types": "normal", "limit": 50})
        assert sidebar.status_code == 200
        assert owner not in [item["id"] for item in sidebar.json()]

        # Any library owner is readable by id, and unknown ids stay 404.
        fetched = client.get(f"/api/artifacts/{first.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["content"]["title"] == "First card"
        assert client.get("/api/artifacts/does-not-exist").status_code == 404

        # The library view lists them, because they are saved artifacts.
        listed = client.get("/api/artifacts", params={"limit": 50})
        assert listed.status_code == 200
        ids = [item["id"] for item in listed.json()]
        assert first.json()["id"] in ids and second.json()["id"] in ids


def test_library_artifacts_require_a_non_blank_source() -> None:
    """An artifact with no conversation must name who created it."""
    payload = _card_payload("Unattributed")
    for metadata in ({}, {"source": ""}, {"source": "   "}, {"source": 7}):
        payload["metadata"] = metadata
        with TestClient(app) as client:
            response = client.post("/api/artifacts", json=payload)
        assert response.status_code == 422, metadata
        assert "metadata.source is required" in response.text


def test_session_owned_artifacts_keep_their_conversation_as_provenance() -> None:
    """The session route is unchanged: the conversation is the attribution."""
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        payload = _card_payload("From a chat")
        payload["metadata"] = {}
        response = client.post(f"/api/agent/{session_id}/artifacts", json=payload)

    assert response.status_code == 201, response.text
    assert response.json()["session_id"] == session_id


def test_library_delete_removes_the_artifact_and_its_assignments() -> None:
    with TestClient(app) as client:
        artifact = client.post("/api/artifacts", json=_card_payload("Delete me")).json()
        tag = client.post("/api/library/tags", json={"path": "Trash/Temp"}).json()
        assert client.put(f"/api/library/tags/{tag['id']}/artifacts/{artifact['id']}").status_code == 200

        deleted = client.delete(f"/api/artifacts/{artifact['id']}")

        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}
        assert client.get(f"/api/artifacts/{artifact['id']}").status_code == 404
        assert client.get("/api/artifacts", params={"limit": 50}).json() == []
        # The taxonomy survives; only the assignment left with the artifact.
        assert client.get("/api/library/tags").json()[0]["total_count"] == 0
        # Deleting it twice answers 404 rather than pretending it worked.
        assert client.delete(f"/api/artifacts/{artifact['id']}").status_code == 404


def test_library_delete_refuses_an_artifact_a_conversation_owns() -> None:
    """Ownership decides: the library interface never deletes a chat's artifact."""
    with TestClient(app) as client:
        client.post("/api/artifacts", json=_card_payload("Library card"))
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        payload = _card_payload("Chat card")
        payload["metadata"] = {}
        chat = client.post(f"/api/agent/{session_id}/artifacts", json=payload).json()

        refused = client.delete(f"/api/artifacts/{chat['id']}")

        assert refused.status_code == 403
        assert "belongs to a conversation" in refused.text
        # It is untouched, and the conversation that owns it still deletes it.
        assert client.get(f"/api/artifacts/{chat['id']}").status_code == 200
        assert client.delete(f"/api/agent/{session_id}/artifacts/{chat['id']}").json() == {"ok": True}


def test_library_delete_refuses_before_any_library_session_exists() -> None:
    """A chat artifact is not library-owned just because no library session exists."""
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        payload = _card_payload("Chat card")
        payload["metadata"] = {}
        chat = client.post(f"/api/agent/{session_id}/artifacts", json=payload).json()

        assert client.delete(f"/api/artifacts/{chat['id']}").status_code == 403
        assert client.delete("/api/artifacts/does-not-exist").status_code == 404


async def test_library_session_service_creates_and_reuses_one_session() -> None:
    service = LibrarySessionService()

    first = await service.get_or_create()
    second = await service.get_or_create()

    assert first == second
    record = await key_value_storage.get(LIBRARY_SESSION_KEY)
    assert record is not None and record.value == first
    summary = await session_storage.get(first)
    assert summary is not None
    assert summary.session_type == SESSION_TYPE_TO_CODE[SessionType.LIBRARY]
    assert summary.title == LIBRARY_SESSION_TITLE


async def test_library_session_service_replaces_a_missing_session() -> None:
    """A session deleted outside the API is replaced, not remembered forever."""
    service = LibrarySessionService()
    original = await service.get_or_create()
    await session_storage.delete(original)

    replacement = await service.get_or_create()

    assert replacement != original
    record = await key_value_storage.get(LIBRARY_SESSION_KEY)
    assert record is not None and record.value == replacement

"""Historical context-composition API tests."""

from fastapi.testclient import TestClient

from zett.application.session_context import session_context_composition_service
from zett.main import app


def test_historical_session_context_composition_is_reconstructed_and_cached() -> None:
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]

        first = client.get(f"/api/agent/sessions/{session_id}/context-composition")
        second = client.get(f"/api/agent/sessions/{session_id}/context-composition")

        assert first.status_code == 200
        assert first.json() == {
            "system_prompt": 1.0,
            "tool_prompt": 0.0,
            "tool_output": 0.0,
            "user": 0.0,
            "assistant": 0.0,
        }
        assert second.json() == first.json()
        assert session_context_composition_service.get(session_id) is not None


def test_live_context_composition_is_returned_and_deleted_with_session() -> None:
    ratios = {
        "system_prompt": 0.1,
        "tool_prompt": 0.2,
        "tool_output": 0.3,
        "user": 0.15,
        "assistant": 0.25,
    }
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        session_context_composition_service.remember(session_id, ratios)

        response = client.get(f"/api/agent/sessions/{session_id}/context-composition")

        assert response.status_code == 200
        assert response.json() == ratios
        assert client.delete(f"/api/agent/sessions/{session_id}").json() == {"ok": True}
        assert session_context_composition_service.get(session_id) is None


def test_context_composition_requires_an_existing_session() -> None:
    with TestClient(app) as client:
        response = client.get("/api/agent/sessions/missing/context-composition")

    assert response.status_code == 404

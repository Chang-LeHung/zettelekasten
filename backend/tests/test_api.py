"""End-to-end tests for the categorized asynchronous FastAPI interface."""

import inspect
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from zett_agent import AssistantMessage, ModelEvent, ModelRequest, ModelResponse

from zett.application.routes import agent as agent_routes
from zett.infra.dao import provider_storage
from zett.main import app


def _provider_payload(**changes):
    payload = {
        "name": "Local test",
        "provider": "openai_compatible",
        "model": "test-model",
        "base_url": "https://example.invalid/v1",
        "api_key": "secret",
        "temperature": 0.3,
        "enabled": True,
    }
    payload.update(changes)
    return payload


def _card_content(title: str = "Card") -> dict[str, object]:
    return {
        "artifact_type": "card",
        "card_type": "note",
        "title": title,
        "summary": "Summary",
        "suggested_tags": [{"path": "Engineering/Python", "existing": False, "confidence": 0.9}],
        "keywords": ["python"],
        "content": "# Body",
    }


def test_business_route_handlers_are_async():
    routes = [route for route in app.routes if getattr(route, "path", "").startswith("/api/")]
    assert routes
    assert all(inspect.iscoroutinefunction(route.endpoint) for route in routes)


def test_session_asset_and_artifact_http_lifecycle():
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        other_id = client.post("/api/agent/start").json()["conversation_id"]

        text = client.post(
            f"/api/agent/{session_id}/assets/text",
            json={"name": "Context", "content": "asset body"},
        )
        assert text.status_code == 201
        assert text.json()["text_content"] == "asset body"

        uploaded = client.post(
            f"/api/agent/{session_id}/assets/upload?name=image.png",
            content=b"png-content",
            headers={"content-type": "image/png"},
        )
        assert uploaded.status_code == 201
        asset_id = uploaded.json()["id"]
        assert uploaded.json()["asset_type"] == "image"
        assert client.get(f"/api/agent/{session_id}/assets/{asset_id}/content").content == b"png-content"
        assert client.get(f"/api/agent/{other_id}/assets/{asset_id}").status_code == 404

        created = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": _card_content(), "raw_content": "raw"},
        )
        assert created.status_code == 201
        artifact_id = created.json()["id"]
        assert created.json()["status"] == "draft"
        assert client.get(f"/api/agent/{other_id}/artifacts/{artifact_id}").status_code == 404

        updated = client.put(
            f"/api/agent/{session_id}/artifacts/{artifact_id}",
            json={"content": _card_content("Updated")},
        )
        assert updated.json()["content"]["title"] == "Updated"
        assert updated.json()["version"] == 2
        saved = client.post(f"/api/agent/{session_id}/artifacts/{artifact_id}/save")
        assert saved.json()["status"] == "saved"
        assert [item["id"] for item in client.get("/api/artifacts?statuses=saved").json()] == [artifact_id]

        detail = client.get(f"/api/agent/sessions/{session_id}").json()
        assert [item["id"] for item in detail["artifacts"]] == [artifact_id]
        assert {item["id"] for item in detail["assets"]} == {text.json()["id"], asset_id}
        assert client.delete(f"/api/agent/{session_id}/artifacts/{artifact_id}").json() == {"ok": True}
        assert client.delete(f"/api/agent/{session_id}/assets/{asset_id}").json() == {"ok": True}


def test_provider_http_lifecycle_preserves_blank_update_key():
    with TestClient(app) as client:
        created = client.post("/api/ai/providers", json=_provider_payload())
        assert created.status_code == 201
        provider_id = created.json()["id"]
        assert created.json()["api_key_configured"] is True
        assert created.json()["temperature"] == 0.3
        assert "api_key" not in created.json()

        updated = client.put(
            f"/api/ai/providers/{provider_id}",
            json=_provider_payload(name="Renamed", api_key=""),
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed"
        connection = provider_storage.resolve_connection(provider_id)
        assert connection is not None and connection.api_key is not None
        assert connection.api_key.get_secret_value() == "secret"
        assert client.get(f"/api/ai/providers/{provider_id}").json()["id"] == provider_id
        assert client.delete(f"/api/ai/providers/{provider_id}").json() == {"ok": True}
        assert client.get(f"/api/ai/providers/{provider_id}").status_code == 404


class FakeModel:
    """Deterministic provider used to exercise the real Agent and SSE stack."""

    closed = False

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        assert request.messages[-1].role == "user"
        yield ModelEvent.reasoning("checking")
        yield ModelEvent.text("answer")
        yield ModelEvent.completed(ModelResponse(AssistantMessage(content="answer", reasoning="checking")))

    async def aclose(self) -> None:
        self.closed = True


def test_agent_stream_uses_provider_neutral_events_and_persists_messages(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        response = client.post(
            f"/api/agent/{session_id}/messages",
            json={
                "raw_content": "question",
                "provider_id": provider_id,
                "reasoning_effort": "medium",
                "messages": [],
            },
        )
        assert response.status_code == 200
        assert "event: reasoning_delta\n" in response.text
        assert "event: text_delta\n" in response.text
        assert "event: run_completed\n" in response.text
        detail = client.get(f"/api/agent/sessions/{session_id}").json()
        assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
        assert detail["messages"][1]["reasoning_content"] == "checking"
    assert model.closed

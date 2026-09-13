"""End-to-end tests for the categorized asynchronous FastAPI interface."""

import base64
import inspect
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from zett_agent import (
    AssistantMessage,
    ImageBytesSource,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolMessage,
    UserMessage,
)

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
        "response": True,
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
        image_content = client.get(f"/api/agent/{session_id}/assets/{asset_id}/content")
        assert image_content.content == b"png-content"
        assert image_content.headers["content-disposition"].startswith("inline;")
        assert image_content.headers["x-content-type-options"] == "nosniff"
        assert image_content.headers["content-security-policy"] == "sandbox; default-src 'none'"
        assert client.get(f"/api/agent/{other_id}/assets/{asset_id}").status_code == 404

        uploaded_file = client.post(
            f"/api/agent/{session_id}/assets/upload?name=notes.txt",
            content=b"download me",
            headers={"content-type": "application/octet-stream"},
        )
        file_content = client.get(f"/api/agent/{session_id}/assets/{uploaded_file.json()['id']}/content")
        assert file_content.headers["content-disposition"].startswith("attachment;")

        uploaded_pdf = client.post(
            f"/api/agent/{session_id}/assets/upload?name=paper.pdf",
            content=b"%PDF-1.7\n",
            headers={"content-type": "application/pdf"},
        )
        pdf_content = client.get(f"/api/agent/{session_id}/assets/{uploaded_pdf.json()['id']}/content")
        assert pdf_content.content == b"%PDF-1.7\n"
        assert pdf_content.headers["content-disposition"].startswith("inline;")

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
        assert {item["id"] for item in detail["assets"]} == {
            text.json()["id"],
            asset_id,
            uploaded_file.json()["id"],
            uploaded_pdf.json()["id"],
        }
        assert client.delete(f"/api/agent/{session_id}/artifacts/{artifact_id}").json() == {"ok": True}
        assert client.delete(f"/api/agent/{session_id}/assets/{asset_id}").json() == {"ok": True}


def test_provider_http_lifecycle_preserves_blank_update_key():
    with TestClient(app) as client:
        created = client.post("/api/ai/providers", json=_provider_payload())
        assert created.status_code == 201
        provider_id = created.json()["id"]
        assert created.json()["api_key_configured"] is True
        assert created.json()["temperature"] == 0.3
        assert created.json()["response"] is True
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
        assert connection.metadata["response"] is True
        assert client.get(f"/api/ai/providers/{provider_id}").json()["id"] == provider_id
        assert client.delete(f"/api/ai/providers/{provider_id}").json() == {"ok": True}
        assert client.get(f"/api/ai/providers/{provider_id}").status_code == 404


def test_provider_http_rejects_response_mode_for_native_non_responses_adapter():
    with TestClient(app) as client:
        result = client.post("/api/ai/providers", json=_provider_payload(provider="anthropic", response=True))

    assert result.status_code == 422


def test_provider_http_normalizes_responses_compatible_mode():
    with TestClient(app) as client:
        created = client.post(
            "/api/ai/providers",
            json=_provider_payload(provider="responses-compatible", response=False),
        )
        assert created.status_code == 201
        assert created.json()["provider"] == "responses_compatible"
        assert created.json()["response"] is True
        assert client.delete(f"/api/ai/providers/{created.json()['id']}").json() == {"ok": True}

        missing_url = client.post(
            "/api/ai/providers",
            json=_provider_payload(provider="responses_compatible", base_url=""),
        )
        assert missing_url.status_code == 422


class FakeModel:
    """Deterministic provider used to exercise the real Agent and SSE stack."""

    closed = False

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
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


def test_pasted_image_is_persisted_in_the_user_message_not_session_assets(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    image_bytes = b"not-decoded-by-the-provider-test"
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        response = client.post(
            f"/api/agent/{session_id}/messages",
            json={
                "raw_content": "Before image, after image.",
                "provider_id": provider_id,
                "parts": [
                    {"type": "text", "text": "Before image, "},
                    {
                        "type": "image",
                        "name": "clipboard.png",
                        "mime_type": "image/png",
                        "data_base64": base64.b64encode(image_bytes).decode("ascii"),
                    },
                    {"type": "text", "text": "after image."},
                ],
            },
        )

        assert response.status_code == 200
        message = model.requests[0].messages[-1]
        assert isinstance(message, UserMessage)
        assert [type(part).__name__ for part in message.parts] == ["TextContent", "ImageContent", "TextContent"]
        image = message.parts[1]
        assert isinstance(image.source, ImageBytesSource)
        assert image.source.data == image_bytes
        detail = client.get(f"/api/agent/sessions/{session_id}").json()
        assert detail["assets"] == []
        assert detail["messages"][0]["parts"] == [
            {"type": "text", "text": "Before image, "},
            {
                "type": "image",
                "name": "clipboard.png",
                "mime_type": "image/png",
                "content_url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}",
            },
            {"type": "text", "text": "after image."},
        ]


def test_message_images_reject_empty_turns_invalid_base64_and_oversized_collections(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    monkeypatch.setattr(agent_routes.settings, "max_asset_size_bytes", 3)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        endpoint = f"/api/agent/{session_id}/messages"
        common = {"provider_id": provider_id, "raw_content": ""}

        assert client.post(endpoint, json=common).status_code == 422
        invalid = client.post(
            endpoint,
            json={
                **common,
                "parts": [{"type": "image", "name": "bad.png", "mime_type": "image/png", "data_base64": "%%%"}],
            },
        )
        assert invalid.status_code == 422
        oversized = client.post(
            endpoint,
            json={
                **common,
                "parts": [
                    {
                        "type": "image",
                        "name": "large.png",
                        "mime_type": "image/png",
                        "data_base64": base64.b64encode(b"1234").decode("ascii"),
                    }
                ],
            },
        )
        assert oversized.status_code == 413

        monkeypatch.setattr(agent_routes.settings, "max_asset_size_bytes", 100)
        too_many = client.post(
            endpoint,
            json={
                **common,
                "parts": [
                    {
                        "type": "image",
                        "name": f"image-{index}.png",
                        "mime_type": "image/png",
                        "data_base64": base64.b64encode(b"x").decode("ascii"),
                    }
                    for index in range(33)
                ],
            },
        )
        assert too_many.status_code == 422
        assert "up to 32 images" in too_many.text

        assert client.put("/api/settings", json={"max_message_images": 1}).status_code == 200
        configured_limit = client.post(
            endpoint,
            json={
                **common,
                "parts": [
                    {
                        "type": "image",
                        "name": f"configured-{index}.png",
                        "mime_type": "image/png",
                        "data_base64": base64.b64encode(b"x").decode("ascii"),
                    }
                    for index in range(2)
                ],
            },
        )
        assert configured_limit.status_code == 422
        assert "up to 1 image" in configured_limit.text
    assert model.requests == []


class TitleAwareModel:
    """Serve a normal answer and submit a typed title in private Agent runs."""

    def __init__(self) -> None:
        self.title_requests = 0
        self.closed = False

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        title_tool = next((item for item in request.tools if item.name == "submit_session_title"), None)
        if title_tool is None:
            yield ModelEvent.text("I will help design the editor.")
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="I will help design the editor.")))
            return
        self.title_requests += 1
        if isinstance(request.messages[-1], ToolMessage):
            yield ModelEvent.completed(ModelResponse(AssistantMessage(content="Title submitted.")))
            return
        yield ModelEvent.completed(
            ModelResponse(
                AssistantMessage(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="title-call",
                            name="submit_session_title",
                            arguments={"title": "Designing a knowledge card editor"},
                        )
                    ],
                )
            )
        )

    async def aclose(self) -> None:
        self.closed = True


def test_first_successful_turn_generates_the_session_title_once(monkeypatch):
    models: list[TitleAwareModel] = []

    def model_factory(_connection):
        model = TitleAwareModel()
        models.append(model)
        return model

    monkeypatch.setattr(agent_routes, "create_model", model_factory)
    monkeypatch.setattr("zett.application.session_titles.create_model", model_factory)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        payload = {
            "raw_content": "Help me design a knowledge card editor",
            "provider_id": provider_id,
            "reasoning_effort": "medium",
            "messages": [],
        }

        assert client.post(f"/api/agent/{session_id}/messages", json=payload).status_code == 200
        assert client.get(f"/api/agent/sessions/{session_id}").json()["title"] == "Designing a knowledge card editor"
        assert client.post(f"/api/agent/{session_id}/messages", json=payload).status_code == 200

    assert len(models) == 3
    assert sum(model.title_requests > 0 for model in models) == 1
    assert all(model.closed for model in models)

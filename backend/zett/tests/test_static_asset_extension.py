"""The static-asset instruction names the upload endpoint and never changes."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from zett_agent.messages import (
    AssistantMessage,
    SystemMessage,
)
from zett_agent.model import (
    ModelEvent,
    ModelRequest,
    ModelResponse,
)

from zett.application.api.routes import agent as agent_routes
from zett.config import settings
from zett.main import app


class RecordingModel:
    """Answer every turn while recording the request the Agent composed."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        yield ModelEvent.completed(ModelResponse(AssistantMessage(content="answer")))

    async def aclose(self) -> None:
        return None


def _provider_payload() -> dict[str, object]:
    return {
        "name": "Local test",
        "provider": "openai_compatible",
        "model": "test-model",
        "base_url": "https://example.invalid/v1",
        "api_key": "secret",
        "temperature": 0.3,
        "response": True,
        "enabled": True,
    }


def _static_asset_messages(request: ModelRequest) -> list[SystemMessage]:
    """Return the static-asset instruction the Agent composed, when present."""
    return [
        message
        for message in request.messages
        if isinstance(message, SystemMessage) and message.content.startswith("# Static assets")
    ]


def _offline_models(monkeypatch: pytest.MonkeyPatch, model: RecordingModel) -> None:
    """Keep both the turn and the background title task off the network."""
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    monkeypatch.setattr("zett.application.agent.session_titles.create_model", lambda _connection: RecordingModel())


def _run_turns(monkeypatch: pytest.MonkeyPatch, contents: tuple[str, ...]) -> RecordingModel:
    """Run one turn per content string and return the recording model."""
    model = RecordingModel()
    _offline_models(monkeypatch, model)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        endpoint = f"/api/agent/{session_id}/messages"
        for content in contents:
            response = client.post(endpoint, json={"raw_content": content, "provider_id": provider_id})
            assert response.status_code == 200
    return model


def test_static_asset_message_names_the_upload_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _run_turns(monkeypatch, ("Publish the compiled paper.",))

    messages = _static_asset_messages(model.requests[0])
    assert len(messages) == 1
    instruction = messages[0].content
    assert f"http://{settings.host}:{settings.port}/api/assets/upload" in instruction
    assert "--data-binary" in instruction
    assert "/api/assets`" in instruction


def test_static_asset_message_is_byte_identical_across_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _run_turns(monkeypatch, ("First turn.", "Second turn."))

    first, second = (_static_asset_messages(request) for request in model.requests[:2])
    assert len(first) == 1 and len(second) == 1
    # A byte-identical prefix message keeps the provider prompt cache valid.
    assert first[0].content == second[0].content


def test_static_asset_message_reaches_a_wildcard_bind_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "host", "0.0.0.0")
    model = _run_turns(monkeypatch, ("Publish something.",))

    instruction = _static_asset_messages(model.requests[0])[0].content
    # A shell command cannot dial a wildcard address, so the message names loopback.
    assert "0.0.0.0" not in instruction
    assert f"http://127.0.0.1:{settings.port}/api/assets" in instruction

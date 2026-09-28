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


def test_static_asset_message_names_the_library_and_its_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """The library's purpose is policy a tool list cannot state, so it stays."""
    model = _run_turns(monkeypatch, ("Publish the compiled paper.",))

    messages = _static_asset_messages(model.requests[0])
    assert len(messages) == 1
    instruction = messages[0].content
    assert "global Static Assets library" in instruction
    assert "upload_static_asset" in instruction
    assert "set_asset_tags" in instruction
    assert "create_asset_tag" in instruction
    assert "list_asset_tags" in instruction
    # The library is reached through tools, so the message carries no shell
    # recipe: an endpoint documented here would be one more thing to keep true.
    assert "curl" not in instruction
    assert "--data-binary" not in instruction


def test_static_asset_message_is_byte_identical_across_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _run_turns(monkeypatch, ("First turn.", "Second turn."))

    first, second = (_static_asset_messages(request) for request in model.requests[:2])
    assert len(first) == 1 and len(second) == 1
    # A byte-identical prefix message keeps the provider prompt cache valid.
    assert first[0].content == second[0].content


def test_static_asset_message_carries_no_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """The message describes the library, not how to reach it.

    A route in the leading system prefix is one more thing that has to stay true
    across the file, and the tools already name the way in.
    """
    monkeypatch.setattr(settings, "host", "0.0.0.0")
    model = _run_turns(monkeypatch, ("Publish something.",))

    instruction = _static_asset_messages(model.requests[0])[0].content
    assert "0.0.0.0" not in instruction
    assert "http://" not in instruction
    assert "/api/" not in instruction

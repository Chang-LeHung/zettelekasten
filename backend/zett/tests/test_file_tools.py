"""Zett's file tools: one ``read`` for text and a local image, and no second path tool."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from zett_agent.messages import AssistantMessage, SystemMessage
from zett_agent.model import ModelEvent, ModelRequest, ModelResponse

from zett.application.api.routes import agent as agent_routes
from zett.main import app

FILE_TOOLS = {"read", "glob", "grep", "write_file", "edit", "bash"}


class RecordingModel:
    """Answer one turn and keep the request so a test can read its tools."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        yield ModelEvent.completed(ModelResponse(AssistantMessage(content="answer")))

    async def aclose(self) -> None:
        return None


def _turn(monkeypatch: pytest.MonkeyPatch, *, multimodal: bool = True) -> tuple[set[str], list[str]]:
    model = RecordingModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    monkeypatch.setattr("zett.application.agent.session_titles.create_model", lambda _connection: RecordingModel())
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post(
            "/api/ai/providers",
            json={
                "name": "Local test",
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "https://example.invalid/v1",
                "api_key": "secret",
                "multimodal": multimodal,
                "enabled": True,
            },
        ).json()["id"]
        sent = client.post(
            f"/api/agent/{session_id}/messages",
            json={"raw_content": "Hello.", "provider_id": provider_id},
        )
        assert sent.status_code == 200
    assert len(model.requests) == 1
    request = model.requests[0]
    names = {tool.name for tool in request.tools}
    instructions = [message.content for message in request.messages if isinstance(message, SystemMessage)]
    return names, instructions


def test_read_replaces_read_file_and_covers_local_images(monkeypatch: pytest.MonkeyPatch) -> None:
    names, instructions = _turn(monkeypatch)

    assert FILE_TOOLS <= names
    # `read` returns text and a local image, so neither single-purpose tool is offered.
    assert "read_file" not in names
    assert "view_image" not in names
    # Removing a file is `bash`, so no separate delete tool competes with it.
    assert "delete_file" not in names
    environment = [text for text in instructions if text.startswith("# Filesystem environment")]
    assert len(environment) == 1
    assert "`read` returns a text line range or" in environment[0]


def test_text_only_model_gets_read_file_instead_of_read(monkeypatch: pytest.MonkeyPatch) -> None:
    names, instructions = _turn(monkeypatch, multimodal=False)

    assert "read_file" in names
    assert "read" not in names
    environment = [text for text in instructions if text.startswith("# Filesystem environment")][0]
    assert "cannot read images" in environment

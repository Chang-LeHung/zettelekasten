"""Coverage for the session files written when a message is submitted."""

import base64
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.testclient import TestClient
from zett_agent import AssistantMessage, ModelEvent, ModelRequest, ModelResponse, SystemMessage

from zett.application.files.object_store import session_directory_key
from zett.application.routes import agent as agent_routes
from zett.infra.files.object_store import get_object_store
from zett.main import app

IMAGE_BYTES = b"\x89PNG\r\n\x1a\n session upload payload"


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


def _image_part(name: str = "clipboard.png") -> dict[str, str]:
    encoded = base64.b64encode(IMAGE_BYTES).decode("ascii")
    return {
        "type": "image",
        "name": name,
        "mime_type": "image/png",
        "content_url": f"data:image/png;base64,{encoded}",
    }


def _submitted_uploads(session_id: str) -> list[Path]:
    """List every stored upload of one session in submission order."""
    directory = get_object_store().resolve(session_directory_key(session_id)) / "uploads"
    return sorted(directory.iterdir()) if directory.is_dir() else []


def _session_files_messages(request: ModelRequest) -> list[SystemMessage]:
    """Return the session-files instruction the Agent composed, when present."""
    return [
        message
        for message in request.messages
        if isinstance(message, SystemMessage) and message.content.startswith("# Session files")
    ]


def _offline_models(monkeypatch, model: RecordingModel) -> None:
    """Keep both the turn and the background title task off the network."""
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    monkeypatch.setattr("zett.application.agent.session_titles.create_model", lambda _connection: RecordingModel())


def test_submitted_message_images_are_written_under_the_session_directory(monkeypatch) -> None:
    model = RecordingModel()
    _offline_models(monkeypatch, model)
    # A pasted screenshot arrives without an extension, so its MIME type supplies one.
    parts = [_image_part(), _image_part("Pasted image")]
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]

        response = client.post(
            f"/api/agent/{session_id}/messages",
            json={"raw_content": "Look at this.", "provider_id": provider_id, "parts": parts},
        )

        assert response.status_code == 200
        uploads = _submitted_uploads(session_id)
        assert len(uploads) == 2
        assert [path.read_bytes() for path in uploads] == [IMAGE_BYTES, IMAGE_BYTES]
        assert uploads[0].name.endswith("-1-clipboard.png")
        assert uploads[1].name.endswith("-2-Pasted-image.png")
        # The immutable user message keeps its data URL, and a submitted image
        # stays a message attachment rather than a curated session asset.
        detail = client.get(f"/api/agent/sessions/{session_id}").json()
        assert detail["assets"] == []
        user_message = next(message for message in detail["messages"] if message["role"] == "user")
        assert user_message["parts"] == parts


def test_session_files_message_names_the_directory_and_never_changes(monkeypatch) -> None:
    model = RecordingModel()
    _offline_models(monkeypatch, model)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        endpoint = f"/api/agent/{session_id}/messages"

        # A turn that stores an image and a turn that stores nothing must produce
        # the same prefix, so submitting an upload never breaks prompt caching.
        for content, parts in (("First turn.", [_image_part()]), ("Second turn.", [])):
            response = client.post(
                endpoint,
                json={"raw_content": content, "provider_id": provider_id, "parts": parts},
            )
            assert response.status_code == 200

        first, second = (_session_files_messages(request) for request in model.requests[:2])
        assert len(first) == 1
        assert len(second) == 1
        assert str(get_object_store().resolve(session_directory_key(session_id))) in first[0].content
        # A byte-identical prefix message keeps the provider prompt cache valid.
        assert first[0].content == second[0].content
        # The instruction names the directory only; no uploaded content reaches it.
        assert _submitted_uploads(session_id)[0].name not in first[0].content


def test_deleting_a_session_removes_its_uploaded_files(monkeypatch) -> None:
    model = RecordingModel()
    _offline_models(monkeypatch, model)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        response = client.post(
            f"/api/agent/{session_id}/messages",
            json={"raw_content": "Look.", "provider_id": provider_id, "parts": [_image_part()]},
        )
        assert response.status_code == 200
        assert len(_submitted_uploads(session_id)) == 1

        assert client.delete(f"/api/agent/sessions/{session_id}").status_code == 200

        assert not get_object_store().resolve(session_directory_key(session_id)).exists()

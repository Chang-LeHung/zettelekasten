"""End-to-end tests for the categorized asynchronous FastAPI interface."""

import asyncio
import base64
import inspect
import json
import threading
from collections.abc import AsyncIterator
from contextlib import aclosing

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from zett_agent import (
    AgentRunConfig,
    AssistantMessage,
    ExternalEvent,
    ImageBytesSource,
    ImageContent,
    ModelEvent,
    ModelRequest,
    ModelResponse,
    TextContent,
    ToolCall,
    ToolMessage,
    UserMessage,
)

from zett.application.provider_connections import ProviderConnectionTestError
from zett.application.routes import agent as agent_routes
from zett.application.routes import providers as provider_routes
from zett.application.session_context import SESSION_CONTEXT_KEY_PREFIX
from zett.application.session_preferences import SESSION_MODEL_KEY_PREFIX
from zett.infra.dao import provider_storage
from zett.infra.database import session_scope
from zett.infra.models import KeyValueModel
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


def _slides_content(title: str = "Deck") -> dict[str, object]:
    return {
        "artifact_type": "slides",
        "title": title,
        "subtitle": "A concise presentation",
        "summary": "Two focused slides",
        "suggested_tags": [],
        "keywords": ["slides"],
        "content": "# Opening\n\nA clear premise.\n\n---\n\n## Next step\n\n- One action",
    }


def test_business_route_handlers_are_async():
    routes = [route for route in app.routes if getattr(route, "path", "").startswith("/api/")]
    assert routes
    assert all(inspect.iscoroutinefunction(route.endpoint) for route in routes)


async def test_active_request_registry_rejects_overlap_and_allows_next_request() -> None:
    registry = agent_routes.ActiveRequestRegistry()
    first = AgentRunConfig(session_id="shared", request_id="first")
    second = AgentRunConfig(session_id="shared", request_id="second")

    await registry.reserve(first)
    assert await registry.pending("shared") is True
    await registry.reserve(AgentRunConfig(session_id="independent", request_id="parallel"))
    assert await registry.pending("independent") is True
    with pytest.raises(HTTPException) as conflict:
        await registry.reserve(second)
    assert conflict.value.status_code == 409

    # A stale request cannot release a reservation that it does not own.
    await registry.remove(second)
    with pytest.raises(HTTPException):
        await registry.reserve(second)

    await registry.remove(first)
    assert await registry.pending("shared") is False
    await registry.reserve(second)
    await registry.remove(second)


async def test_active_request_registry_routes_only_after_agent_binding() -> None:
    registry = agent_routes.ActiveRequestRegistry()
    config = AgentRunConfig(session_id="events", request_id="request")
    event = ExternalEvent(name="answer", payload={"choice": "A"})

    assert await registry.emit("missing", event) is None
    await registry.reserve(config)
    assert await registry.emit("events", event) == []

    class RecordingAgent:
        def __init__(self) -> None:
            self.received = []

        def emit_external_event(self, received_event, *, config):
            self.received.append((received_event, config))
            return ["ask-user"]

    agent = RecordingAgent()
    await registry.bind(config, agent)  # type: ignore[arg-type]

    assert await registry.emit("events", event) == ["ask-user"]
    assert agent.received == [(event, config)]


def test_steer_endpoint_routes_typed_external_event(monkeypatch) -> None:
    captured: list[tuple[str, ExternalEvent]] = []

    async def emit(session_id: str, event: ExternalEvent) -> list[str]:
        captured.append((session_id, event))
        return ["SteeringExtension"]

    monkeypatch.setattr(agent_routes.active_requests, "emit", emit)

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/session-1/steer",
            json={
                "raw_content": "Explain first.",
                "parts": [
                    {"type": "text", "text": "Explain first."},
                    {
                        "type": "image",
                        "name": "clipboard.png",
                        "mime_type": "image/png",
                        "data_base64": "aW1hZ2U=",
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "accepted_by": ["SteeringExtension"]}
    assert captured == [
        (
            "session-1",
            ExternalEvent(
                name="steering_message",
                payload={
                    "session_id": "session-1",
                    "message": UserMessage(
                        content=[
                            TextContent("Explain first."),
                            ImageContent(
                                source=ImageBytesSource(b"image", "image/png"),
                                alt_text="clipboard.png",
                            ),
                        ]
                    ),
                },
            ),
        )
    ]


async def test_active_request_registry_requires_reservation_before_binding() -> None:
    registry = agent_routes.ActiveRequestRegistry()
    config = AgentRunConfig(session_id="unreserved", request_id="request")

    with pytest.raises(RuntimeError, match="without its active request reservation"):
        await registry.bind(config, object())  # type: ignore[arg-type]


async def test_closing_stream_releases_session_and_provider_for_next_turn(monkeypatch) -> None:
    """A browser disconnect must cancel ownership instead of wedging the session."""
    entered = threading.Event()

    class BlockingModel:
        def __init__(self) -> None:
            self.closed = False

        async def stream(self, request):
            entered.set()
            yield ModelEvent.text("partial")
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            self.closed = True

    model = BlockingModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    agent_config = agent_routes.ZettelkastenAgentConfig
    monkeypatch.setattr(
        agent_routes,
        "ZettelkastenAgentConfig",
        lambda **options: agent_config(**options, skill_roots=(), mcp_config_path=None),
    )
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        payload = agent_routes.AnalyzeRequest.model_validate(
            {
                "raw_content": "wait",
                "provider_id": provider_id,
                "reasoning_effort": "medium",
                "messages": [],
            }
        )
        response = await agent_routes.stream_message(session_id, payload)

        async def consume() -> None:
            async with aclosing(response.body_iterator) as stream:
                async for _ in stream:
                    pass

        consumer = asyncio.create_task(consume())
        assert await asyncio.to_thread(entered.wait, 1)
        assert await agent_routes.active_requests.pending(session_id) is True

        # Starlette uses task cancellation when the HTTP client disconnects.
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

        assert await agent_routes.active_requests.pending(session_id) is False
        assert model.closed is True

        # The released session can immediately reserve a fresh request.
        next_config = AgentRunConfig(session_id=session_id, request_id="next")
        await agent_routes.active_requests.reserve(next_config)
        await agent_routes.active_requests.remove(next_config)


async def test_agent_setup_failure_releases_reservation_and_closes_provider(monkeypatch) -> None:
    class ClosingModel:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    async def fail_create(_config, _storage):
        raise RuntimeError("agent setup failed")

    model = ClosingModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    monkeypatch.setattr(agent_routes.ZettelkastenAgentConfig, "create", fail_create)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        payload = agent_routes.AnalyzeRequest.model_validate(
            {"raw_content": "setup", "provider_id": provider_id, "reasoning_effort": "medium"}
        )

        with pytest.raises(RuntimeError, match="agent setup failed"):
            await agent_routes.stream_message(session_id, payload)

        assert await agent_routes.active_requests.pending(session_id) is False
        assert model.closed is True


async def test_provider_stream_failure_emits_error_and_releases_request(monkeypatch) -> None:
    class FailingModel:
        def __init__(self) -> None:
            self.closed = False

        async def stream(self, request):
            raise RuntimeError("provider stream failed")
            yield  # pragma: no cover - preserve the async-generator protocol

        async def aclose(self) -> None:
            self.closed = True

    model = FailingModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        payload = agent_routes.AnalyzeRequest.model_validate(
            {"raw_content": "fail", "provider_id": provider_id, "reasoning_effort": "medium"}
        )
        response = await agent_routes.stream_message(session_id, payload)

        chunks = [chunk async for chunk in response.body_iterator]

        assert any("event: error" in chunk and "provider stream failed" in chunk for chunk in chunks)
        assert await agent_routes.active_requests.pending(session_id) is False
        assert model.closed is True


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
        slides = client.post(
            f"/api/agent/{session_id}/artifacts",
            json={"content": _slides_content(), "raw_content": "make slides"},
        )
        assert slides.status_code == 201
        slides_id = slides.json()["id"]
        assert slides.json()["content"]["artifact_type"] == "slides"
        assert client.post(f"/api/agent/{session_id}/artifacts/{slides_id}/save").status_code == 200
        saved_artifacts = client.get("/api/artifacts?statuses=saved").json()
        assert {item["id"] for item in saved_artifacts} == {artifact_id, slides_id}
        assert [item["id"] for item in client.get("/api/artifacts?artifact_types=slides").json()] == [slides_id]

        detail = client.get(f"/api/agent/sessions/{session_id}").json()
        assert [item["id"] for item in detail["artifacts"]] == [slides_id, artifact_id]
        assert {item["id"] for item in detail["assets"]} == {
            text.json()["id"],
            asset_id,
            uploaded_file.json()["id"],
            uploaded_pdf.json()["id"],
        }
        assert client.delete(f"/api/agent/{session_id}/artifacts/{artifact_id}").json() == {"ok": True}
        assert client.delete(f"/api/agent/{session_id}/artifacts/{slides_id}").json() == {"ok": True}
        assert client.delete(f"/api/agent/{session_id}/assets/{asset_id}").json() == {"ok": True}


def test_artifact_api_rejects_ambiguous_slide_boundaries() -> None:
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        content = _slides_content()
        content["content"] = "# First\n --- \n# Second"

        response = client.post(f"/api/agent/{session_id}/artifacts", json={"content": content})

        assert response.status_code == 422
        assert "slide separators must be exactly" in response.text


async def test_provider_http_lifecycle_preserves_blank_update_key():
    with TestClient(app) as client:
        created = client.post("/api/ai/providers", json=_provider_payload())
        assert created.status_code == 201
        provider_id = created.json()["id"]
        assert created.json()["api_key_configured"] is True
        assert created.json()["temperature"] == 0.3
        assert created.json()["response"] is True
        assert "api_key" not in created.json()
        listed = client.get("/api/ai/providers").json()
        listed_provider = [provider for provider in listed if provider["id"] == provider_id][0]
        assert "api_key" not in listed_provider

        detail = client.get(f"/api/ai/providers/{provider_id}")
        assert detail.status_code == 200
        assert detail.json()["api_key"] == "secret"

        updated = client.put(
            f"/api/ai/providers/{provider_id}",
            json=_provider_payload(name="Renamed", api_key=""),
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed"
        connection = await provider_storage.resolve_connection(provider_id)
        assert connection is not None and connection.api_key is not None
        assert connection.api_key.get_secret_value() == "secret"
        assert connection.metadata["response"] is True
        updated_detail = client.get(f"/api/ai/providers/{provider_id}").json()
        assert updated_detail["id"] == provider_id
        assert updated_detail["api_key"] == "secret"
        assert client.delete(f"/api/ai/providers/{provider_id}").json() == {"ok": True}
        assert client.get(f"/api/ai/providers/{provider_id}").status_code == 404


async def test_provider_http_does_not_store_a_failed_connection(monkeypatch):
    async def reject(_connection) -> None:
        raise ProviderConnectionTestError("Provider stream ended without a response")

    monkeypatch.setattr(provider_routes, "verify_provider_connection", reject)
    with TestClient(app) as client:
        response = client.post("/api/ai/providers", json=_provider_payload())

    assert response.status_code == 422
    assert "without a response" in response.text
    assert await provider_storage.list() == []


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


class ShellFakeModel:
    """Request one harmless shell command, then answer with its result."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        message = (
            AssistantMessage(tool_calls=(ToolCall("shell-1", "run_shell", {"command": "printf approved"}),))
            if len(self.requests) == 1
            else AssistantMessage(content="shell complete")
        )
        yield ModelEvent.completed(ModelResponse(message))

    async def aclose(self) -> None:
        return None


async def test_agent_stream_uses_provider_neutral_events_and_persists_messages(monkeypatch):
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
        # Every model step publishes the live context ratios the composer ring reads.
        assert "event: custom\n" in response.text
        assert '"name":"context_composition"' in response.text
        detail = client.get(f"/api/agent/sessions/{session_id}").json()
        assert any(message["role"] == "system" for message in detail["messages"])
        assert [message["role"] for message in detail["messages"] if message["role"] != "system"] == [
            "user",
            "assistant",
        ]
        activity = client.get("/api/settings/usage-activity?days=1").json()
        assert activity[0]["requests"] == 1
        assert activity[0]["total_tokens"] == 0
        assistant = next(message for message in detail["messages"] if message["role"] == "assistant")
        assert assistant["reasoning_content"] == "checking"
    assert model.closed
    async with session_scope() as session:
        record = await session.scalar(
            select(KeyValueModel).where(KeyValueModel.key == f"{SESSION_CONTEXT_KEY_PREFIX}{session_id}")
        )
    assert record is not None
    ratios = json.loads(record.value)
    assert set(ratios) == {"system_prompt", "tool_prompt", "tool_output", "user", "assistant"}
    assert sum(ratios.values()) == pytest.approx(1)


def test_agent_shell_allow_all_skips_approval_events(monkeypatch):
    model = ShellFakeModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        response = client.post(
            f"/api/agent/{session_id}/messages",
            json={
                "raw_content": "run a command",
                "provider_id": provider_id,
                "reasoning_effort": "off",
                "shell_approval_mode": "allow_all",
                "messages": [],
            },
        )
        approval = client.get(f"/api/agent/sessions/{session_id}/shell-approval")

    assert response.status_code == 200
    assert "event: shell_approval_requested\n" not in response.text
    assert "event: tool_completed\n" in response.text
    assert "approved" in response.text
    assert approval.json() == {"mode": "allow_all"}


def test_session_shell_approval_settings_round_trip():
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        assert client.get(f"/api/agent/sessions/{session_id}/shell-approval").json() == {"mode": "review"}

        updated = client.put(
            f"/api/agent/sessions/{session_id}/shell-approval",
            json={"mode": "allow_all"},
        )

        assert updated.status_code == 200
        assert updated.json() == {"mode": "allow_all"}
        assert client.get(f"/api/agent/sessions/{session_id}/shell-approval").json() == {"mode": "allow_all"}


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
        user_message = next(message for message in detail["messages"] if message["role"] == "user")
        assert user_message["parts"] == [
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


async def test_first_successful_turn_generates_the_session_title_once(monkeypatch):
    models: list[TitleAwareModel] = []
    request_agents = []
    original_agent_factory = agent_routes.ZettelkastenAgentConfig.create

    def model_factory(_connection):
        model = TitleAwareModel()
        models.append(model)
        return model

    async def agent_factory(config, storage):
        agent = await original_agent_factory(config, storage)
        request_agents.append(agent)
        return agent

    monkeypatch.setattr(agent_routes, "create_model", model_factory)
    monkeypatch.setattr(agent_routes.ZettelkastenAgentConfig, "create", agent_factory)
    monkeypatch.setattr("zett.application.session_titles.create_model", model_factory)
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        assert client.get(f"/api/agent/sessions/{session_id}").json()["title"] == "新会话"
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        payload = {
            "raw_content": "Help me design a knowledge card editor",
            "provider_id": provider_id,
            "reasoning_effort": "medium",
            "messages": [],
        }

        assert client.get(f"/api/agent/sessions/{session_id}/model").json() is None
        assert client.post(f"/api/agent/{session_id}/messages", json=payload).status_code == 200
        assert client.get(f"/api/agent/sessions/{session_id}").json()["title"] == "Designing a knowledge card editor"
        assert (
            client.put(
                "/api/settings",
                json={"max_message_images": 32, "max_turn_iterations": 9},
            ).status_code
            == 200
        )
        assert client.post(f"/api/agent/{session_id}/messages", json=payload).status_code == 200
        assert client.get(f"/api/agent/sessions/{session_id}/model").json() == {
            "provider_id": provider_id,
            "provider": "openai_compatible",
            "model": "test-model",
        }

    async with session_scope() as session:
        revisions = list(
            await session.scalars(
                select(KeyValueModel)
                .where(KeyValueModel.key == f"{SESSION_MODEL_KEY_PREFIX}{session_id}")
                .order_by(KeyValueModel.version)
            )
        )
        versions = [revision.version for revision in revisions]
    assert len(revisions) == 1
    assert versions == [2]

    assert len(models) == 3
    assert len(request_agents) == 2
    assert request_agents[0] is not request_agents[1]
    assert [agent.agent.max_iterations for agent in request_agents] == [36, 9]
    assert sum(model.title_requests > 0 for model in models) == 1
    assert all(model.closed for model in models)

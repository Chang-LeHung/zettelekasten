"""Provider web search: the settings rule, the declared server tool, and the request it reaches."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from zett_agent.messages import AssistantMessage
from zett_agent.model import ModelEvent, ModelRequest, ModelResponse, ServerToolDefinition

from zett.agent.web_search import web_search_tools
from zett.application.api.routes import agent as agent_routes
from zett.main import app
from zett.schemas import ProviderConnection, ProviderType, ProviderWrite
from zett.schemas.providers import default_web_search_name, web_search_error


def _connection(provider: ProviderType, model: str, **metadata: object) -> ProviderConnection:
    return ProviderConnection(
        id="provider-1",
        provider=provider,
        model=model,
        api_key=SecretStr("secret"),
        metadata=metadata,
    )


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Search test",
        "provider": "anthropic_compatible",
        "model": "deepseek-flash",
        "base_url": "https://example.invalid",
        "api_key": "secret",
        "response": False,
        "web_search": True,
        "enabled": True,
    }
    payload.update(changes)
    return payload


class RecordingModel:
    """Answer one turn and keep the request so a test can read its server tools."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        yield ModelEvent.completed(ModelResponse(AssistantMessage(content="answer")))

    async def aclose(self) -> None:
        return None


def test_each_protocol_declares_the_search_tool_it_understands() -> None:
    assert default_web_search_name(ProviderType.OPENAI, "gpt", response=True) == "web_search"
    # OpenAI-style adapters send hosted tools on Chat Completions too.
    assert default_web_search_name(ProviderType.OPENAI, "gpt", response=False) == "web_search"
    assert default_web_search_name(ProviderType.OPENAI_COMPATIBLE, "m", response=False) == "web_search"
    assert default_web_search_name(ProviderType.RESPONSES_COMPATIBLE, "m", response=True) == "web_search"
    assert default_web_search_name(ProviderType.ANTHROPIC, "claude", response=False) == "web_search_20260318"
    assert default_web_search_name(ProviderType.GOOGLE, "gemini", response=False) == "google_search"
    assert default_web_search_name(ProviderType.OLLAMA, "llama", response=False) is None
    # DeepSeek's Anthropic endpoint answers the older versioned type.
    assert default_web_search_name(ProviderType.ANTHROPIC_COMPATIBLE, "deepseek-flash", response=False) == (
        "web_search_20250305"
    )


@pytest.mark.parametrize(
    ("provider", "model", "response", "name", "fragment"),
    [
        (ProviderType.ANTHROPIC_COMPATIBLE, "deepseek-flash", False, None, None),
        (ProviderType.ANTHROPIC_COMPATIBLE, "deepseek-v4-pro", False, None, "flash"),
        (ProviderType.RESPONSES_COMPATIBLE, "deepseek-flash", True, None, "Anthropic API"),
        (ProviderType.DEEPSEEK, "deepseek-v4-flash", True, None, "Anthropic API"),
        (ProviderType.OLLAMA, "llama", False, "web_search", "Ollama"),
        (ProviderType.ANTHROPIC_COMPATIBLE, "claude", False, "gateway:search", None),
        (ProviderType.OPENAI, "gpt", True, "bad name!", "letters, digits"),
    ],
)
def test_web_search_support_depends_on_protocol_and_model(
    provider: ProviderType, model: str, response: bool, name: str | None, fragment: str | None
) -> None:
    error = web_search_error(provider, model, response=response, name=name)

    if fragment is None:
        assert error is None
    else:
        assert error is not None and fragment in error


def test_the_write_model_refuses_an_unsupported_search_before_persistence() -> None:
    with pytest.raises(ValidationError, match="Anthropic API"):
        ProviderWrite(
            name="x",
            provider=ProviderType.DEEPSEEK,
            model="deepseek-v4-flash",
            metadata={"response": True, "web_search": True},
        )
    with pytest.raises(ValidationError, match="boolean"):
        ProviderWrite(name="x", provider=ProviderType.OPENAI, model="gpt", metadata={"web_search": "yes"})
    # A disabled toggle never blocks an otherwise ordinary configuration.
    ProviderWrite(name="x", provider=ProviderType.OLLAMA, model="llama", metadata={"web_search": False})


def test_search_tool_follows_the_connection() -> None:
    assert web_search_tools(_connection(ProviderType.OPENAI, "gpt", response=True)) == ()
    assert web_search_tools(_connection(ProviderType.OPENAI, "gpt", response=True, web_search=True)) == (
        ServerToolDefinition("web_search"),
    )
    # Anthropic's wire schema wants a name beside the versioned type.
    assert web_search_tools(_connection(ProviderType.ANTHROPIC_COMPATIBLE, "deepseek-flash", web_search=True)) == (
        ServerToolDefinition("web_search_20250305", {"name": "web_search"}),
    )
    # A stored name overrides the default, and nothing is declared for a protocol without a default.
    assert web_search_tools(
        _connection(ProviderType.ANTHROPIC, "claude", web_search=True, web_search_name="web_search_20250305")
    ) == (ServerToolDefinition("web_search_20250305", {"name": "web_search"}),)
    assert web_search_tools(_connection(ProviderType.OPENAI_COMPATIBLE, "m", web_search=True)) == (
        ServerToolDefinition("web_search"),
    )
    assert web_search_tools(
        _connection(ProviderType.OPENAI_COMPATIBLE, "m", web_search=True, web_search_name="gateway:search")
    ) == (ServerToolDefinition("gateway:search"),)


def test_provider_http_stores_and_reports_the_search_setting() -> None:
    with TestClient(app) as client:
        created = client.post("/api/ai/providers", json=_payload(web_search_name="web_search_20250305"))
        assert created.status_code == 201
        assert created.json()["web_search"] is True
        assert created.json()["web_search_name"] == "web_search_20250305"

        provider_id = created.json()["id"]
        cleared = client.put(f"/api/ai/providers/{provider_id}", json=_payload(web_search=False, api_key=""))
        assert cleared.status_code == 200
        assert cleared.json()["web_search"] is False
        assert cleared.json()["web_search_name"] is None

        blank = client.post("/api/ai/providers", json=_payload(web_search_name="   "))
        assert blank.status_code == 201
        assert blank.json()["web_search_name"] is None


def test_provider_http_rejects_search_the_endpoint_cannot_run() -> None:
    with TestClient(app) as client:
        pro = client.post("/api/ai/providers", json=_payload(model="deepseek-v4-pro"))
        chat = client.post(
            "/api/ai/providers",
            json=_payload(provider="openai_compatible", model="deepseek-flash"),
        )
        responses = client.post(
            "/api/ai/providers",
            json=_payload(provider="responses_compatible", model="deepseek-flash", response=True),
        )

    assert pro.status_code == 422 and "flash" in pro.text
    assert chat.status_code == 422 and "Anthropic API" in chat.text
    assert responses.status_code == 422 and "Anthropic API" in responses.text


def _search_tools_of_one_turn(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> list[ServerToolDefinition]:
    model = RecordingModel()
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    monkeypatch.setattr("zett.application.agent.session_titles.create_model", lambda _connection: RecordingModel())
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=payload).json()["id"]
        sent = client.post(
            f"/api/agent/{session_id}/messages",
            json={"raw_content": "Hello.", "provider_id": provider_id},
        )
        assert sent.status_code == 200
    assert len(model.requests) == 1
    return list(model.requests[0].server_tools)


def test_a_turn_carries_the_search_tool_only_when_the_provider_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    searching = _search_tools_of_one_turn(monkeypatch, _payload())
    plain = _search_tools_of_one_turn(monkeypatch, _payload(web_search=False))

    assert searching == [ServerToolDefinition("web_search_20250305", {"name": "web_search"})]
    assert plain == []

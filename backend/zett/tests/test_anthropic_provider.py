"""Anthropic and Anthropic-compatible connections: endpoint shape, validation, and a real round trip."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from zett_agent.messages import UserMessage
from zett_agent.model import ModelEventType, ModelRequest, ReasoningEffort

from zett.agent.model_factory import anthropic_base_url, create_model
from zett.main import app
from zett.schemas import ProviderConnection, ProviderType


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (None, None),
        ("", None),
        ("https://api.anthropic.com", "https://api.anthropic.com"),
        ("https://api.anthropic.com/", "https://api.anthropic.com"),
        ("https://api.anthropic.com/v1", "https://api.anthropic.com"),
        ("https://proxy.example.com/anthropic/v1/", "https://proxy.example.com/anthropic"),
        ("  https://x.test/v1  ", "https://x.test"),
        ("http://tds.com:8787/v1/messages", "http://tds.com:8787"),
        ("http://tds.com:8787/v1/messages/", "http://tds.com:8787"),
        ("https://x.test/anthropic/v1/messages", "https://x.test/anthropic"),
        ("https://x.test/messages", "https://x.test"),
        ("https://x.test/v10", "https://x.test/v10"),
    ],
)
def test_the_sdk_root_never_carries_its_own_v1(given: str | None, expected: str | None) -> None:
    assert anthropic_base_url(given) == expected


def _connection(provider: ProviderType, base_url: str | None) -> ProviderConnection:
    return ProviderConnection(
        id="p", provider=provider, model="claude-x", base_url=base_url, api_key=SecretStr("secret")
    )


async def test_both_anthropic_types_build_the_messages_adapter_and_refuse_a_missing_compatible_url() -> None:
    from zett_agent.providers.anthropic import AnthropicProvider

    for provider in (ProviderType.ANTHROPIC, ProviderType.ANTHROPIC_COMPATIBLE):
        model = create_model(_connection(provider, "https://example.test/v1"))
        try:
            assert isinstance(model, AnthropicProvider)
            assert str(model._client.base_url).rstrip("/") == "https://example.test"
        finally:
            await model.aclose()
    with pytest.raises(ValueError, match="base URL"):
        create_model(_connection(ProviderType.ANTHROPIC_COMPATIBLE, None))


async def test_a_round_trip_reaches_messages_once_whichever_way_the_address_is_written() -> None:
    """The failure this guards: `…/v1` was requested at `/v1/v1/messages`."""
    seen: list[tuple[str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("x-api-key"), request.headers.get("anthropic-version")))
        events = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "m",
                        "type": "message",
                        "role": "assistant",
                        "model": "x",
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 3, "output_tokens": 0},
                    },
                },
            ),
            (
                "content_block_start",
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            ),
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "OK"}},
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}},
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
        body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

    from zett_agent.providers.anthropic import AnthropicProvider

    for written in ("https://relay.test", "https://relay.test/v1", "https://relay.test/v1/"):
        seen.clear()
        model = AnthropicProvider(
            model="claude-x",
            api_key="secret",
            base_url=anthropic_base_url(written) or "",
            transport=httpx.MockTransport(handler),
        )
        try:
            request = ModelRequest(messages=[UserMessage(content="hi")], reasoning_effort=ReasoningEffort.OFF)
            events = [event async for event in model.stream(request)]
        finally:
            await model.aclose()
        assert any(event.type == ModelEventType.RESPONSE for event in events), written
        assert seen == [("/v1/messages", "secret", "2023-06-01")], written


def test_http_accepts_an_anthropic_compatible_provider_only_with_a_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from zett.application.api.routes import providers as provider_routes

    async def accept(_connection: ProviderConnection) -> None:
        return None

    monkeypatch.setattr(provider_routes, "verify_provider_connection", accept)
    payload = {"name": "Relay", "provider": "anthropic-compatible", "model": "glm-x", "api_key": "k", "enabled": True}
    with TestClient(app) as client:
        assert client.post("/api/ai/providers", json=payload).status_code == 422
        created = client.post("/api/ai/providers", json={**payload, "base_url": "https://relay.test/anthropic"})
        assert created.status_code == 201
        assert created.json()["provider"] == "anthropic_compatible"
        assert client.get("/api/ai/providers").json()[0]["provider"] == "anthropic_compatible"
        assert (
            client.post(
                "/api/ai/providers", json={**payload, "base_url": "https://r.test", "response": True}
            ).status_code
            == 422
        )

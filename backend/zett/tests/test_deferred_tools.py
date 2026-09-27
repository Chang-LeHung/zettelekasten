"""Deferred tools follow the provider protocol: search on Responses, plain elsewhere."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from zett_agent.agent import (
    Agent,
    AgentRunConfig,
)
from zett_agent.extensions.base import (
    AgentExtension,
)
from zett_agent.extensions.tool_search import (
    ToolSearchExtension,
)
from zett_agent.messages import (
    AssistantMessage,
    SystemMessage,
)
from zett_agent.model import (
    ModelEvent,
    ModelRequest,
    ModelResponse,
)
from zett_agent.providers.openai import (
    OpenAIProvider,
)
from zett_agent.tools.base import (
    tool,
)

from zett.agent.extensions.deferred_tools import DeferredToolExtension
from zett.agent.model_factory import uses_responses_api
from zett.application.api.routes import agent as agent_routes
from zett.main import app

#: Zett tool that must be deferred on the Responses API and visible everywhere else.
DEFERRED_TOOL = "create_scheduled_task"
SECOND_DEFERRED_TOOL = "list_scheduled_tasks"
#: A tool that stays in the request even on the Responses API.
VISIBLE_TOOL = "create_artifact"
SEARCH_TOOL = "tool_search"


class ProtocolModel:
    """Record the tools the Agent offers while answering one turn."""

    def __init__(self, *, response: bool) -> None:
        self.response = response
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


def _offered_tools(monkeypatch: pytest.MonkeyPatch, *, response: bool) -> dict[str, bool]:
    """Run one API turn and return the offered tool names with their deferred flag."""
    return _turn(monkeypatch, response=response)[0]


def _turn(monkeypatch: pytest.MonkeyPatch, *, response: bool) -> tuple[dict[str, bool], list[str]]:
    """Run one API turn and return its offered tools plus its system instructions."""
    model = ProtocolModel(response=response)
    monkeypatch.setattr(agent_routes, "create_model", lambda _connection: model)
    # The background title task builds its own model, so it needs the same stub.
    monkeypatch.setattr(
        "zett.application.agent.session_titles.create_model",
        lambda _connection: ProtocolModel(response=response),
    )
    with TestClient(app) as client:
        session_id = client.post("/api/agent/start").json()["conversation_id"]
        provider_id = client.post("/api/ai/providers", json=_provider_payload()).json()["id"]
        response_payload = client.post(
            f"/api/agent/{session_id}/messages",
            json={"raw_content": "Hello.", "provider_id": provider_id},
        )
        assert response_payload.status_code == 200
    assert len(model.requests) == 1
    request = model.requests[0]
    instructions = [message.content for message in request.messages if isinstance(message, SystemMessage)]
    return {tool.name: tool.deferred for tool in request.tools}, instructions


def test_responses_api_hides_deferred_tools_behind_the_search_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    offered = _offered_tools(monkeypatch, response=True)

    # The search tool stands in for every deferred definition, which stays out of the request.
    assert offered.get(SEARCH_TOOL) is False
    assert DEFERRED_TOOL not in offered
    assert SECOND_DEFERRED_TOOL not in offered
    assert offered[VISIBLE_TOOL] is False


def test_other_protocols_receive_every_tool_as_an_ordinary_function(monkeypatch: pytest.MonkeyPatch) -> None:
    offered = _offered_tools(monkeypatch, response=False)

    # No protocol without tool search may see the search tool, and nothing stays hidden.
    assert SEARCH_TOOL not in offered
    assert offered[DEFERRED_TOOL] is False
    assert offered[SECOND_DEFERRED_TOOL] is False
    assert set(offered.values()) == {False}


def test_only_the_responses_api_tells_the_model_how_to_search(monkeypatch: pytest.MonkeyPatch) -> None:
    _, searchable = _turn(monkeypatch, response=True)
    _, plain = _turn(monkeypatch, response=False)

    hints = [instruction for instruction in searchable if instruction.startswith("# Tool search")]
    assert len(hints) == 1
    # The model cannot search for what it does not know exists.
    assert "tool_search" in hints[0]
    assert "scheduled tasks" in hints[0]
    # A protocol without the search tool must not advertise one.
    assert not [instruction for instruction in plain if instruction.startswith("# Tool search")]


def test_only_responses_adapters_report_the_protocol() -> None:
    assert uses_responses_api(OpenAIProvider(model="gpt-5", api_key="key", response=True)) is True
    assert uses_responses_api(OpenAIProvider(model="gpt-5", api_key="key")) is False
    assert uses_responses_api(None) is False
    # A model type that is not one of Zett's adapters must never be mistaken for it.
    assert uses_responses_api(ProtocolModel(response=False)) is False


def test_the_protocol_rewrite_runs_before_any_deferred_filter() -> None:
    """The request must be rewritten before an extension filters it again.

    A filter that ran first would drop every deferred definition, including the
    ones this extension reveals for a protocol without tool search.
    """
    assert DeferredToolExtension.priority < ToolSearchExtension.priority


@tool(deferred=True)
async def deferred_probe(value: str) -> str:
    """Return the probe value.

    Args:
        value: Anything the caller wants echoed.

    Snippet:
        deferred_probe(value="x")

    Guidelines:
        - Probe tool for tests only.
    """
    return value


class ProbeExtension(AgentExtension):
    """Register one deferred tool so a filter has something to remove."""

    async def on_tool(self, context) -> None:
        context.register_tool(deferred_probe)


async def test_a_registered_search_filter_cannot_strip_revealed_tools() -> None:
    """A chat-protocol run keeps its tools even when the search filter is installed."""
    model = ProtocolModel(response=False)
    agent = await Agent.create(
        model,
        config=AgentRunConfig(session_id="probe"),
        # Registration order is deliberately worst first: the search filter is last.
        extensions=[ProbeExtension(), DeferredToolExtension(), ToolSearchExtension()],
    )

    await agent.run("hello")

    offered = {tool.name: tool.deferred for tool in model.requests[0].tools}
    assert offered == {"deferred_probe": False}

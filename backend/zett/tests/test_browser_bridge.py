"""Browser RPC isolation and WebSocket tests; all sessions use temporary SQLite."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect
from zett_agent.agent import Agent, AgentRunConfig
from zett_agent.messages import AssistantMessage, ToolCall, ToolMessage
from zett_agent.model import ModelEvent, ModelResponse

from zett.agent.config import ZettelkastenAgentConfig
from zett.agent.extensions.browser import BrowserExtension
from zett.agent.zettelkasten import ZettelkastenAgent
from zett.application.agent.browser import (
    BrowserBridge,
    BrowserConnection,
    BrowserDOMPatch,
    BrowserInteraction,
    BrowserPageQuery,
    BrowserReply,
    BrowserResult,
    BrowserUnavailableError,
    browser_bridge,
)
from zett.application.api.routes import agent as agent_routes
from zett.application.api.schemas import AnalyzeRequest
from zett.infra.persistence.dao import session_storage
from zett.main import app
from zett.schemas import AgentSessionCreate


async def test_connection_is_live_session_bound_and_not_replaced() -> None:
    first = await session_storage.create(AgentSessionCreate(title="One"))
    second = await session_storage.create(AgentSessionCreate(title="Two"))
    bridge = BrowserBridge()
    peer = await bridge.connect(first.session_id, AsyncMock())
    assert bridge.require(first.session_id, peer.token) is peer
    with pytest.raises(BrowserUnavailableError):
        bridge.require(second.session_id, peer.token)
    with pytest.raises(BrowserUnavailableError):
        await bridge.connect(first.session_id, AsyncMock())
    bridge.disconnect(peer)
    with pytest.raises(BrowserUnavailableError):
        bridge.require(first.session_id, peer.token)
    with pytest.raises(BrowserUnavailableError):
        await bridge.connect("missing", AsyncMock())


async def test_correlated_reply_parallel_rejection_and_disconnect() -> None:
    queue = asyncio.Queue()
    peer = BrowserConnection("session", "token", queue.put)
    task = asyncio.create_task(peer.call("snapshot"))
    command = await queue.get()
    with pytest.raises(BrowserUnavailableError, match="pending"):
        await peer.call("snapshot")
    peer.resolve(BrowserReply(type="result", id="wrong", ok=True, result="null"))
    assert not task.done()
    peer.resolve(BrowserReply(type="result", id=command["id"], ok=True, result='{"title":"Page"}'))
    result = await task
    assert json.loads(result.result) == {"title": "Page"}
    task = asyncio.create_task(peer.call("snapshot"))
    await queue.get()
    peer.close()
    with pytest.raises(BrowserUnavailableError, match="disconnected"):
        await task
    assert not peer.pending


async def test_cancellation_cleans_pending_calls_without_replay() -> None:
    """A cancelled turn stays cancelled and still tells the panel to drop consent.

    The command is already queued when the cancel lands, which is the timing
    Python 3.10/3.11 `asyncio.wait_for` can answer with a result instead of the
    cancellation.
    """
    queue = asyncio.Queue()
    peer = BrowserConnection("session", "token", queue.put)
    task = asyncio.create_task(peer.call("snapshot"))
    command = await queue.get()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert peer.pending == {}
    assert await queue.get() == {"type": "cancel", "id": command["id"]}


@pytest.mark.parametrize(
    "changes",
    [
        {"selector": ""},
        {"selector": " "},
        {"selector": "a" * 501},
        {"value": "x" * 10001},
        {"value": True},
        {"action": "set_checked", "value": "true"},
        {"action": "execute"},
        {"action": "click"},
        {"code": "alert(1)"},
        {"html": "<script>alert(1)</script>"},
    ],
)
def test_dom_patch_validation(changes) -> None:
    with pytest.raises(ValidationError):
        BrowserDOMPatch.model_validate(
            {"action": "fill", "selector": "#name", "value": "Ada", "description": "Fill name", **changes}
        )


def test_dom_query_and_checkbox_validation() -> None:
    assert BrowserDOMPatch(action="set_checked", selector="#opt", value=False, description="Uncheck").value is False
    with pytest.raises(ValidationError):
        BrowserPageQuery(selector=" ")


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "drag", "target_selector": None},
        {"action": "press_key", "key": None},
        {"action": "scroll", "direction": "down", "distance": None},
        {"action": "click", "key": "Enter"},
        {"action": "click", "target_selector": "#other"},
        {"action": "click", "direction": "down", "distance": 100},
        {"action": "execute_js"},
    ],
)
def test_browser_interaction_rejects_mismatched_arguments(changes) -> None:
    with pytest.raises(ValidationError):
        BrowserInteraction.model_validate(
            {
                "action": "click",
                "selector": "#button",
                "description": "Click button",
                **changes,
            }
        )


def test_browser_interaction_accepts_bounded_actions() -> None:
    assert (
        BrowserInteraction(
            action="drag",
            selector="#source",
            target_selector="#target",
            description="Move item",
        ).action
        == "drag"
    )
    assert (
        BrowserInteraction(
            action="press_key",
            selector="#field",
            key="Enter",
            description="Send form",
        ).key
        == "Enter"
    )
    assert (
        BrowserInteraction(
            action="scroll",
            selector="#list",
            direction="down",
            distance=600,
            description="See more",
        ).distance
        == 600
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": True, "result": "NaN"},
        {"ok": True, "result": "not JSON"},
        {"ok": True, "result": '"' + "中" * 30000 + '"'},
        {"ok": False, "error": " "},
        {"ok": "true", "result": "null"},
    ],
)
def test_result_validation(payload) -> None:
    with pytest.raises(ValidationError):
        BrowserResult.model_validate(payload)


def test_websocket_extension_origin_handshake_and_heartbeat() -> None:
    with TestClient(app) as client:
        session = client.post("/api/agent/start").json()["conversation_id"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/agent/{session}/browser", headers={"origin": "https://example.com"}):
                pass
        with client.websocket_connect(
            f"/api/agent/{session}/browser", headers={"origin": "chrome-extension://" + "a" * 32}
        ) as socket:
            ready = socket.receive_json()
            assert ready["type"] == "ready"
            assert len(ready["token"]) == 43
            socket.send_json({"type": "ping"})
            assert socket.receive_json() == {"type": "pong"}
            socket.send_json({"type": "result", "id": "late", "ok": True, "result": "null"})
            socket.send_json({"type": "ping"})
            assert socket.receive_json() == {"type": "pong"}
        assert not browser_bridge.connections


async def test_web_requests_do_not_register_browser_tools_and_invalid_tokens_fail_early(monkeypatch) -> None:
    session = await session_storage.create(AgentSessionCreate(title="Normal"))
    config = ZettelkastenAgentConfig(
        session_id=session.session_id,
        agent_plugins=(),
        skill_roots=(),
        mcp_config_path=None,
    )
    assert config.browser_connection is None
    # Inspect extension wiring without making a provider request.
    captured = {}

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("zett.agent.zettelkasten.Agent", FakeAgent)
    ZettelkastenAgent(config)
    assert not any(isinstance(item, BrowserExtension) for item in captured["extensions"])
    resolve = AsyncMock()
    monkeypatch.setattr(agent_routes.provider_storage, "resolve_connection", resolve)
    with pytest.raises(Exception) as error:
        await agent_routes._prepare_agent_request(
            session.session_id, AnalyzeRequest(raw_content="hi", provider_id="p", browser_token="a" * 43)
        )
    assert error.value.status_code == 409
    resolve.assert_not_called()


async def test_agent_browser_tool_roundtrip() -> None:
    """The runtime tool invokes the bridge and feeds its receipt back to a model."""
    peer = BrowserConnection("browser-test", "token", AsyncMock())
    calls = []

    async def send(payload):
        if payload["type"] != "command":
            return
        calls.append(payload)
        peer.resolve(BrowserReply(type="result", id=payload["id"], ok=True, result='{"filled":true}'))

    peer.send = send

    class Model:
        step = 0

        async def stream(self, request):
            assert {tool.name for tool in request.tools} == {
                "get_browser_page",
                "update_browser_dom",
                "interact_with_browser",
            }
            if self.step == 0:
                message = AssistantMessage(
                    tool_calls=(
                        ToolCall(
                            "edit",
                            "update_browser_dom",
                            {
                                "change": {
                                    "action": "fill",
                                    "selector": "#name",
                                    "value": "Ada",
                                    "description": "Fill a field",
                                }
                            },
                        ),
                    )
                )
            else:
                result = request.messages[-1]
                assert isinstance(result, ToolMessage) and result.success
                assert json.loads(result.content)["ok"] is True
                message = AssistantMessage(content="Done")
            self.step += 1
            yield ModelEvent.completed(ModelResponse(message))

    agent = Agent(Model(), extensions=(BrowserExtension(peer),))
    await agent.initialize(config=AgentRunConfig(session_id="browser-test"))
    from zett_agent.messages import UserMessage

    events = [
        event
        async for event in agent.stream(
            UserMessage(content="Fill the form"), config=AgentRunConfig(session_id="browser-test")
        )
    ]
    assert events
    assert calls[0]["operation"] == "update"
    assert calls[0]["change"]["value"] == "Ada"
    assert "script" not in calls[0]

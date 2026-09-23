"""Zett channel orchestration over the plugin mechanism."""

import asyncio
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from zett.application.channels import agent as im_agent_module
from zett.application.channels import channel_service
from zett.application.channels.agent import (
    AgentClient,
    AgentEvent,
    AgentEventKind,
    AgentTurnRequest,
    ZettIMAgentClient,
)
from zett.application.channels.service import ChannelService
from zett.application.channels.store import ChannelDraft, ChannelStore
from zett.infra.persistence.dao import provider_storage
from zett.infra.plugins import PluginRegistry, ZettKVStorage
from zett.main import app
from zett.plugins import (
    ChannelCredentials,
    ChannelInboundMessage,
    ChannelLoginChallenge,
    ChannelLoginState,
    ChannelLoginStatus,
    PluginContext,
)
from zett.schemas import (
    ChannelLogin,
    ChannelLoginStart,
    ChannelType,
    ProviderType,
    ProviderWrite,
)


async def _provider() -> str:
    provider = await provider_storage.create(
        ProviderWrite(
            name="IM provider",
            provider=ProviderType.OPENAI_COMPATIBLE,
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="secret",
        )
    )
    return provider.id


class FakeAgent(AgentClient):
    """Return a deterministic stream and record requests."""

    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []

    async def stream_turn(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        yield AgentEvent(type=AgentEventKind.STARTED, session_id="session-1")
        yield AgentEvent(type=AgentEventKind.COMPLETED, session_id="session-1", content="Agent reply")


class FakeWeChatPlugin:
    """Stand-in channel plugin that reports a completed login on first poll."""

    plugin_id = "wechat"
    instances: list[FakeWeChatPlugin] = []

    def __init__(self, context: PluginContext) -> None:
        self.context = context
        self.started = False
        self.stopped = False
        self.sent: list[tuple[str, str]] = []
        self.__class__.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def login(self) -> ChannelLoginChallenge:
        return ChannelLoginChallenge(qr_content="https://example.invalid/qr")

    async def is_login(self) -> ChannelLoginState:
        return ChannelLoginState(
            status=ChannelLoginStatus.CONNECTED,
            message="已连接",
            credentials=ChannelCredentials(
                config={"base_url": "https://ilink.example.invalid"},
                secrets={"bot_token": "token-1"},
            ),
        )

    async def receive(self) -> ChannelInboundMessage:
        await asyncio.sleep(3600)
        raise AssertionError("fake plugin should be cancelled before receiving")

    async def send(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


def _registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.register("wechat", FakeWeChatPlugin)
    return registry


async def test_zett_im_agent_client_streams_normalized_events(monkeypatch) -> None:
    provider_id = await _provider()

    async def fake_run(**kwargs) -> str:
        assert kwargs["message"] == "hello"
        assert kwargs["provider_id"] == provider_id
        return "Agent reply"

    monkeypatch.setattr(im_agent_module, "run_headless_prompt", fake_run)
    events = [
        event
        async for event in ZettIMAgentClient().stream_turn(
            AgentTurnRequest(
                request_id="event-1",
                provider_id=provider_id,
                message="hello",
                reasoning_effort="medium",
                allow_coding=False,
                metadata={"channel_name": "WeChat"},
            )
        )
    ]

    assert events[0].type is AgentEventKind.STARTED
    assert events[0].session_id
    assert events[-1].type is AgentEventKind.COMPLETED
    assert events[-1].content == "Agent reply"


async def test_channel_routes_use_the_plugin_mechanism(monkeypatch) -> None:
    provider_id = await _provider()

    async def fake_start(payload) -> ChannelLogin:
        return ChannelLogin(
            id="onboarding-1",
            provider_id=payload.provider_id,
            name=payload.name,
            status=ChannelLoginStatus.PENDING,
            qr_url="https://example.invalid/page",
            qr_data_url="data:image/svg+xml;base64,abc",
            message="Scan",
            expires_at="2026-09-23T00:05:00Z",
            created_at="2026-09-23T00:00:00Z",
            updated_at="2026-09-23T00:00:00Z",
        )

    monkeypatch.setattr(channel_service, "start_login", fake_start)
    with TestClient(app) as client:
        listed = client.get("/api/channels")
        started = client.post(
            "/api/channels/login/start",
            json={"provider_id": provider_id, "name": "WeChat"},
        )

    assert listed.status_code == 200
    assert listed.json() == []
    assert started.status_code == 201
    assert started.json()["channel_type"] == "wechat"


async def test_channel_service_login_starts_and_sends_through_a_plugin() -> None:
    provider_id = await _provider()
    FakeWeChatPlugin.instances.clear()
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=FakeAgent())
    await service.initialize()

    login = await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))
    assert login.status is ChannelLoginStatus.PENDING
    assert login.qr_data_url and login.qr_data_url.startswith("data:image/svg+xml;base64,")

    connected = await service.poll_login(login.id)
    assert connected is not None
    assert connected.status is ChannelLoginStatus.CONNECTED
    assert connected.channel_id

    channels = await service.list_channels()
    assert [channel.channel_type for channel in channels] == [ChannelType.WECHAT]
    assert await service.provider_referenced(provider_id) is True

    runner = [plugin for plugin in FakeWeChatPlugin.instances if plugin.started]
    assert len(runner) == 1
    await service.send_message(channels[0].id, "user-1", "hi")
    assert runner[0].sent == [("user-1", "hi")]

    await service.shutdown()
    assert runner[0].stopped is True


async def test_channel_store_persists_records_and_dedup_markers() -> None:
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            provider_id="provider-1",
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )

    assert [record.id for record in await store.list_channels()] == [channel.id]
    assert channel.secret_keys == ["bot_token"]
    runtime = await store.get_runtime_channel(channel.id)
    assert runtime is not None
    assert runtime.secrets == {"bot_token": "token-1"}

    assert await store.claim_event(channel.id, "event-1") is True
    assert await store.claim_event(channel.id, "event-1") is False

    await store.bind_agent_session(channel.id, "user-1", "session-1")
    assert await store.agent_session_for(channel.id, "user-1") == "session-1"

    assert await store.delete_channel(channel.id) is True
    assert await store.list_channels() == []


async def test_channel_service_turns_inbound_messages_into_agent_replies() -> None:
    provider_id = await _provider()
    agent = FakeAgent()
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            provider_id=provider_id,
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=agent)

    reply = await service._handle_message(
        channel.id,
        ChannelInboundMessage(event_id="event-1", chat_id="user-1", user_id="user-1", text="hello"),
    )

    assert reply == "Agent reply"
    assert [request.message for request in agent.requests] == ["hello"]
    assert (
        await service._handle_message(
            channel.id,
            ChannelInboundMessage(event_id="event-1", chat_id="user-1", user_id="user-1", text="hello"),
        )
        is None
    )

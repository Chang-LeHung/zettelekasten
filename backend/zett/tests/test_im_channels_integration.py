"""Zett channel orchestration over the plugin mechanism."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from zett._compat import UTC
from zett.application.channels import agent as im_agent_module
from zett.application.channels import channel_service
from zett.application.channels import service as channel_service_module
from zett.application.channels.agent import (
    AgentClient,
    AgentEvent,
    AgentEventKind,
    AgentTurnRequest,
    ZettIMAgentClient,
)
from zett.application.channels.service import ChannelService
from zett.application.channels.store import ChannelDraft, ChannelStore
from zett.infra.persistence.dao import provider_storage, session_storage
from zett.infra.plugins import PluginRegistry, ZettKVStorage
from zett.main import app
from zett.plugins import (
    ChannelCredentials,
    ChannelInboundMessage,
    ChannelLoginChallenge,
    ChannelLoginState,
    ChannelLoginStatus,
    PluginContext,
    PluginError,
)
from zett.schemas import (
    SESSION_TYPE_TO_CODE,
    AgentSessionCreate,
    ChannelLogin,
    ChannelLoginStart,
    ChannelUpdate,
    ProviderType,
    ProviderWrite,
    SessionListOptions,
    SessionType,
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
    plugin_label = "Test WeChat"
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
            message="Connected",
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


class FakeDiscordPlugin(FakeWeChatPlugin):
    """Second platform, registered the way any third-party plugin would be."""

    plugin_id = "discord"
    plugin_label = "Discord"
    instances: list[FakeDiscordPlugin] = []


def _registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.register("wechat", FakeWeChatPlugin)
    return registry


def _registry_for(plugin_class: type) -> PluginRegistry:
    registry = PluginRegistry()
    registry.register("wechat", plugin_class)
    return registry


class FailingStartPlugin:
    """Channel plugin whose ``start`` raises before any receive loop runs."""

    plugin_id = "wechat"

    def __init__(self, context: PluginContext) -> None:
        self.context = context

    async def start(self) -> None:
        raise RuntimeError("plugin exploded during start")

    async def stop(self) -> None:
        return None

    async def login(self) -> ChannelLoginChallenge:
        return ChannelLoginChallenge(qr_content="https://example.invalid/qr")

    async def is_login(self) -> ChannelLoginState:
        return ChannelLoginState(status=ChannelLoginStatus.CONNECTED, message="Connected")

    async def receive(self) -> ChannelInboundMessage:
        await asyncio.sleep(3600)
        raise AssertionError("fake plugin should be cancelled before receiving")

    async def send(self, chat_id: str, text: str) -> None:
        return None


class FailingLoginPlugin(FailingStartPlugin):
    """Channel plugin that cannot begin a login flow."""

    async def start(self) -> None:
        return None

    async def login(self) -> ChannelLoginChallenge:
        raise RuntimeError("plugin exploded during login")


class FailingStopPlugin(FailingStartPlugin):
    """Channel plugin that raises while shutting down."""

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        raise RuntimeError("plugin exploded during stop")


class OutOfContractPlugin(FailingStartPlugin):
    """Channel plugin that returns shapes outside the plugin contract."""

    async def start(self) -> None:
        return None

    async def is_login(self) -> ChannelLoginState:
        return None  # type: ignore[return-value]

    async def receive(self) -> ChannelInboundMessage:
        return None  # type: ignore[return-value]


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


async def test_zett_im_agent_client_opens_a_channel_session(monkeypatch) -> None:
    """An IM conversation is a channel session, not one of the user's own."""
    provider_id = await _provider()

    async def fake_run(**kwargs) -> str:
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

    session_id = events[0].session_id
    assert session_id is not None
    session = await session_storage.get(session_id)
    assert session is not None
    assert session.session_type == SESSION_TYPE_TO_CODE[SessionType.CHANNEL]
    # The conversation sidebar asks only for normal sessions, so a channel chat stays out of it.
    assert await session_storage.list(SessionListOptions(session_types=(SessionType.NORMAL,))) == []
    listed = await session_storage.list(SessionListOptions(session_types=(SessionType.CHANNEL,)))
    assert [item.session_id for item in listed] == [session_id]


async def test_zett_im_agent_client_replaces_a_bound_session_that_is_gone(monkeypatch) -> None:
    """A binding can outlive its session, and the chat must not stay mute."""
    provider_id = await _provider()
    deleted = await session_storage.create(
        AgentSessionCreate(title="WeChat: old chat", session_type=SessionType.CHANNEL)
    )
    assert await session_storage.delete(deleted.session_id)

    async def fake_run(**kwargs) -> str:
        return "Agent reply"

    monkeypatch.setattr(im_agent_module, "run_headless_prompt", fake_run)
    events = [
        event
        async for event in ZettIMAgentClient().stream_turn(
            AgentTurnRequest(
                request_id="event-2",
                provider_id=provider_id,
                agent_session_id=deleted.session_id,
                message="hello again",
                reasoning_effort="medium",
                allow_coding=False,
                metadata={"channel_name": "WeChat"},
            )
        )
    ]

    assert [event.type for event in events] == [AgentEventKind.STARTED, AgentEventKind.COMPLETED]
    replacement = events[0].session_id
    assert replacement is not None and replacement != deleted.session_id
    session = await session_storage.get(replacement)
    assert session is not None
    assert session.session_type == SESSION_TYPE_TO_CODE[SessionType.CHANNEL]


async def test_channel_routes_use_the_plugin_mechanism(monkeypatch) -> None:
    provider_id = await _provider()

    async def fake_start(payload) -> ChannelLogin:
        return ChannelLogin(
            id="onboarding-1",
            channel_type="wechat",
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


async def test_channel_routes_list_installed_plugins() -> None:
    with TestClient(app) as client:
        response = client.get("/api/channels/plugins")

    assert response.status_code == 200
    assert response.json() == [{"channel_type": "wechat", "label": "WeChat"}]


async def test_start_login_requires_a_type_when_multiple_plugins_are_installed() -> None:
    provider_id = await _provider()
    registry = _registry()
    registry.register("discord", FakeDiscordPlugin)
    service = ChannelService(registry=registry, kv=ZettKVStorage(), agent=FakeAgent())

    with pytest.raises(ValueError):
        await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))


async def test_channel_plugins_list_and_route_multiple_platforms() -> None:
    provider_id = await _provider()
    registry = _registry()
    registry.register("discord", FakeDiscordPlugin)
    service = ChannelService(registry=registry, kv=ZettKVStorage(), agent=FakeAgent())

    plugins = await service.list_plugins()
    assert [(item.channel_type, item.label) for item in plugins] == [
        ("discord", "Discord"),
        ("wechat", "Test WeChat"),
    ]

    login = await service.start_login(
        ChannelLoginStart(provider_id=provider_id, channel_type="discord", name="Discord bot")
    )

    assert login.channel_type == "discord"
    assert login.qr_data_url and login.qr_data_url.startswith("data:image/svg+xml;base64,")


async def test_start_login_rejects_an_unknown_channel_type() -> None:
    provider_id = await _provider()
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=FakeAgent())

    with pytest.raises(ValueError):
        await service.start_login(ChannelLoginStart(provider_id=provider_id, channel_type="unknown"))


class ExpiringLoginPlugin(FakeWeChatPlugin):
    """Plugin whose QR flow ends without producing a channel."""

    instances: list[ExpiringLoginPlugin] = []

    async def is_login(self) -> ChannelLoginState:
        return ChannelLoginState(status=ChannelLoginStatus.EXPIRED, message="QR code expired")


async def test_abandoned_login_releases_its_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    """An expired QR flow must not keep a plugin (and its HTTP client) alive."""
    provider_id = await _provider()
    ExpiringLoginPlugin.instances.clear()
    service = ChannelService(registry=_registry_for(ExpiringLoginPlugin), kv=ZettKVStorage(), agent=FakeAgent())

    login = await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))
    finished = await service.poll_login(login.id)

    assert finished is not None and finished.status is ChannelLoginStatus.EXPIRED
    assert ExpiringLoginPlugin.instances[0].stopped is True
    assert await service.poll_login(login.id) is not None

    # The same holds when the QR code times out before anyone polls it with a plugin.
    monkeypatch.setattr(channel_service_module, "LOGIN_TTL", timedelta(seconds=-1))
    timed_out = await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))
    expired = await service.poll_login(timed_out.id)
    assert expired is not None and expired.status is ChannelLoginStatus.EXPIRED
    assert ExpiringLoginPlugin.instances[-1].stopped is True


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
    assert [channel.channel_type for channel in channels] == ["wechat"]
    assert await service.provider_referenced(provider_id) is True

    runner = [plugin for plugin in FakeWeChatPlugin.instances if plugin.started]
    assert len(runner) == 1
    await service.send_message(channels[0].id, "user-1", "hi")
    assert runner[0].sent == [("user-1", "hi")]

    await service.shutdown()
    assert runner[0].stopped is True


async def test_send_message_rejects_blank_input() -> None:
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=FakeAgent())

    with pytest.raises(ValueError):
        await service.send_message("channel-1", "user-1", "   ")
    with pytest.raises(ValueError):
        await service.send_message("channel-1", "   ", "hi")


async def test_channel_store_ignores_blank_identifiers() -> None:
    store = ChannelStore(ZettKVStorage())

    assert await store.get_channel(" ") is None
    assert await store.delete_channel(" ") is False
    assert await store.get_login(" ") is None
    assert await store.claim_event(" ", "event-1") is False
    assert await store.claim_event("channel-1", " ") is False
    assert await store.agent_session_for(" ", "user-1") is None

    await store.bind_agent_session(" ", "user-1", "session-1")
    assert await store.agent_session_for(" ", "user-1") is None


async def test_login_poll_contains_a_plugin_returning_out_of_contract_data() -> None:
    provider_id = await _provider()
    service = ChannelService(registry=_registry_for(OutOfContractPlugin), kv=ZettKVStorage(), agent=FakeAgent())

    login = await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))
    polled = await service.poll_login(login.id)

    assert polled is not None
    assert polled.status is ChannelLoginStatus.FAILED


async def test_receive_loop_contains_out_of_contract_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_id = await _provider()
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
            provider_id=provider_id,
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    monkeypatch.setattr(channel_service_module, "RECEIVE_RETRY_SECONDS", 0.01)
    service = ChannelService(registry=_registry_for(OutOfContractPlugin), kv=ZettKVStorage(), agent=FakeAgent())
    plugin = OutOfContractPlugin(
        PluginContext(plugin_id="wechat", scope_id=channel.id, kv=ZettKVStorage(), config={}, secrets={})
    )

    task = asyncio.create_task(service._consume(channel.id, plugin))
    await asyncio.sleep(0.05)
    assert task.done() is False
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_startup_survives_a_plugin_that_fails_to_start() -> None:
    provider_id = await _provider()
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
            provider_id=provider_id,
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    service = ChannelService(registry=_registry_for(FailingStartPlugin), kv=ZettKVStorage(), agent=FakeAgent())

    await service.initialize()

    assert [record.id for record in await service.list_channels()] == [channel.id]
    with pytest.raises(KeyError):
        await service.send_message(channel.id, "user-1", "hi")
    await service.shutdown()


async def test_login_start_reports_a_plugin_failure_as_a_plugin_error() -> None:
    provider_id = await _provider()
    service = ChannelService(registry=_registry_for(FailingLoginPlugin), kv=ZettKVStorage(), agent=FakeAgent())

    with pytest.raises(PluginError):
        await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))


async def test_channel_deletion_survives_a_plugin_that_fails_to_stop() -> None:
    provider_id = await _provider()
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
            provider_id=provider_id,
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    service = ChannelService(registry=_registry_for(FailingStopPlugin), kv=ZettKVStorage(), agent=FakeAgent())
    await service.initialize()

    assert await service.delete_channel(channel.id) is True
    assert await service.list_channels() == []
    await service.shutdown()


async def test_dedup_markers_are_pruned_after_the_retention_window() -> None:
    """Dedup markers must not grow with every message a chat ever receives."""
    kv = ZettKVStorage()
    store = ChannelStore(kv)
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
            provider_id="provider-1",
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    stale_key = f"im:event:{channel.id}:event-old"
    await kv.set(stale_key, (datetime.now(UTC) - timedelta(days=30)).isoformat())

    assert await store.claim_event(channel.id, "event-new") is True

    assert await kv.get(stale_key) is None
    assert await kv.get(f"im:event:{channel.id}:event-new") is not None
    # A redelivery inside the window is still dropped.
    assert await store.claim_event(channel.id, "event-new") is False


async def test_chat_locks_stay_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A long-lived process talks to unbounded chats, so idle locks are evicted."""
    provider_id = await _provider()
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
            provider_id=provider_id,
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=FakeAgent())
    monkeypatch.setattr(channel_service_module, "LOCK_CACHE_LIMIT", 2)

    for index in range(4):
        chat_id = f"user-{index}"
        reply = await service._handle_message(
            channel.id,
            ChannelInboundMessage(event_id=f"event-{index}", chat_id=chat_id, user_id=chat_id, text="hello"),
        )
        assert reply == "Agent reply"

    assert len(service._locks) <= 2


class FailingAgent(AgentClient):
    """Agent client whose turn fails before it produces a reply."""

    async def stream_turn(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        raise RuntimeError("agent turn failed")
        yield AgentEvent(type=AgentEventKind.FAILED)


class OneMessagePlugin(FakeWeChatPlugin):
    """Plugin that delivers one queued message and then waits for cancellation."""

    instances: list[OneMessagePlugin] = []

    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)
        self.pending: list[ChannelInboundMessage] = []

    async def receive(self) -> ChannelInboundMessage:
        if self.pending:
            return self.pending.pop(0)
        await asyncio.sleep(3600)
        raise AssertionError("fake plugin should be cancelled before receiving again")


async def test_a_failed_turn_answers_instead_of_staying_silent() -> None:
    """Someone waiting in the IM chat must learn that the turn failed."""
    provider_id = await _provider()
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
            provider_id=provider_id,
            config={"base_url": "https://ilink.example.invalid"},
            secrets={"bot_token": "token-1"},
        )
    )
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=FailingAgent())
    plugin = OneMessagePlugin(
        PluginContext(plugin_id="wechat", scope_id=channel.id, kv=ZettKVStorage(), config={}, secrets={})
    )
    plugin.pending.append(ChannelInboundMessage(event_id="event-1", chat_id="user-1", user_id="user-1", text="hello"))

    task = asyncio.create_task(service._consume(channel.id, plugin))
    await asyncio.sleep(0.05)
    assert task.done() is False
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert plugin.sent == [("user-1", channel_service_module.TURN_FAILURE_REPLY)]


async def test_policy_update_keeps_the_channel_and_disabling_stops_it() -> None:
    """A policy edit must not cancel the turn that is running right now."""
    provider_id = await _provider()
    FakeWeChatPlugin.instances.clear()
    service = ChannelService(registry=_registry(), kv=ZettKVStorage(), agent=FakeAgent())
    await service.initialize()
    login = await service.start_login(ChannelLoginStart(provider_id=provider_id, name="WeChat"))
    connected = await service.poll_login(login.id)
    assert connected is not None and connected.channel_id is not None
    channel_id = connected.channel_id
    plugin = FakeWeChatPlugin.instances[-1]
    runner = service._runners[channel_id]

    edited = await service.update_channel(channel_id, ChannelUpdate(allow_coding=False))

    assert edited.allow_coding is False
    assert plugin.stopped is False
    assert service._runners.get(channel_id) is runner

    disabled = await service.update_channel(channel_id, ChannelUpdate(enabled=False))

    assert disabled.enabled is False
    assert plugin.stopped is True
    assert channel_id not in service._runners


async def test_channel_store_persists_records_and_dedup_markers() -> None:
    store = ChannelStore(ZettKVStorage())
    channel = await store.create_channel(
        ChannelDraft(
            name="WeChat",
            channel_type="wechat",
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
            channel_type="wechat",
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

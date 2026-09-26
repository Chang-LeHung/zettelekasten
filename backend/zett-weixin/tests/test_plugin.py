"""zett-weixin plugin behavior against a fake agim client and in-memory KV."""

from typing import Any

import pytest
from agim import (
    InboundMedia,
    InboundMessage,
    LoginCredentials,
    LoginHandshake,
    LoginState,
    LoginStatus,
    MediaKind,
    MediaRejectionReason,
    ReceiveResult,
    RejectedMedia,
)
from zett.plugins import (
    ChannelLoginStatus,
    ChannelMediaKind,
    ChannelMediaRejectionReason,
    JsonValue,
    KVStorage,
    PluginContext,
)

import zett_weixin.plugin as plugin_module
from zett_weixin import WeChatPlugin


class MemoryKV(KVStorage):
    """In-memory stand-in for the KVStorage Zett hands to a plugin."""

    def __init__(self) -> None:
        self.data: dict[str, JsonValue] = {}

    async def get(self, key: str) -> JsonValue | None:
        return self.data.get(key)

    async def set(self, key: str, value: JsonValue) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> bool:
        return self.data.pop(key, None) is not None

    async def iter_prefix(self, prefix: str) -> list[tuple[str, JsonValue]]:
        return sorted((key, value) for key, value in self.data.items() if key.startswith(prefix))


class FakeClient:
    """Scripted stand-in for agim's WeChatClient."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.sent: list[tuple[str, str, str | None]] = []
        self.cursors: list[str | None] = []
        self.inbound_text = "hello"
        self.inbound_media: list[InboundMedia] = []
        self.inbound_rejections: list[RejectedMedia] = []

    async def login(self) -> LoginHandshake:
        return LoginHandshake(
            qr_content="https://weixin.qq.com/qr-1",
            qr_url="https://weixin.qq.com/qr-1",
            state={"qrcode": "qr-1", "base_url": "https://ilink.example.invalid"},
        )

    async def is_login(self, handshake: LoginHandshake, *, verify_code: str | None = None) -> LoginState:
        assert handshake.state["qrcode"] == "qr-1"
        assert verify_code is None
        return LoginState(
            status=LoginStatus.CONNECTED,
            message="Connected",
            credentials=LoginCredentials(
                config={"base_url": "https://ilink.example.invalid"},
                secrets={"bot_token": "token-1"},
            ),
        )

    async def receive(self, cursor: str | None = None) -> ReceiveResult:
        self.cursors.append(cursor)
        return ReceiveResult(
            message=InboundMessage(
                event_id="event-1",
                chat_id="user-1",
                user_id="user-1",
                text=self.inbound_text,
                media=self.inbound_media,
                rejected_media=self.inbound_rejections,
                reply_token="context-1",
            ),
            cursor="cursor-2",
        )

    async def send(self, chat_id: str, text: str, *, context_token: str | None = None) -> None:
        self.sent.append((chat_id, text, context_token))

    async def aclose(self) -> None:
        self.closed = True


def _context(kv: KVStorage, **overrides: Any) -> PluginContext:
    values: dict[str, Any] = {
        "plugin_id": "wechat",
        "scope_id": "channel-1",
        "kv": kv,
        "config": {"base_url": "https://ilink.example.invalid"},
        "secrets": {"bot_token": "token-1"},
    }
    values.update(overrides)
    return PluginContext(**values)


async def test_login_persists_handshake_and_returns_qr(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeClient] = []
    monkeypatch.setattr(
        plugin_module.agim, "WeChatClient", lambda **kwargs: created.append(FakeClient(**kwargs)) or created[-1]
    )
    kv = MemoryKV()
    plugin = WeChatPlugin(_context(kv))

    challenge = await plugin.login()

    assert challenge.qr_content == "https://weixin.qq.com/qr-1"
    assert kv.data["login:handshake"]["state"]["qrcode"] == "qr-1"


async def test_is_login_reads_stored_handshake_and_translates_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_module.agim, "WeChatClient", lambda **kwargs: FakeClient(**kwargs))
    kv = MemoryKV()
    await kv.set(
        "login:handshake",
        {"qr_content": "qr", "qr_url": None, "state": {"qrcode": "qr-1", "base_url": "https://x"}},
    )
    plugin = WeChatPlugin(_context(kv))

    state = await plugin.is_login()

    assert state.status is ChannelLoginStatus.CONNECTED
    assert state.credentials is not None
    assert state.credentials.secrets["bot_token"] == "token-1"


async def test_is_login_without_handshake_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_module.agim, "WeChatClient", lambda **kwargs: FakeClient(**kwargs))
    plugin = WeChatPlugin(_context(MemoryKV()))

    state = await plugin.is_login()

    assert state.status is ChannelLoginStatus.EXPIRED


async def test_receive_persists_cursor_and_context_token(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[FakeClient] = []

    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(plugin_module.agim, "WeChatClient", factory)
    kv = MemoryKV()
    await kv.set("receive:cursor", "cursor-1")
    plugin = WeChatPlugin(_context(kv))
    await plugin.start()

    message = await plugin.receive()

    assert message.event_id == "event-1"
    assert kv.data["receive:cursor"] == "cursor-2"
    assert kv.data["reply:context:user-1"] == "context-1"
    assert clients[-1].cursors == ["cursor-1"]
    await plugin.stop()


async def test_receive_carries_media_into_the_plugin_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        client.inbound_text = ""
        client.inbound_media = [
            InboundMedia(kind=MediaKind.IMAGE, media_type="image/png", name="photo.png", data=b"png-bytes")
        ]
        return client

    monkeypatch.setattr(plugin_module.agim, "WeChatClient", factory)
    plugin = WeChatPlugin(_context(MemoryKV()))
    await plugin.start()

    message = await plugin.receive()

    assert message.text == ""
    assert len(message.media) == 1
    assert message.media[0].kind is ChannelMediaKind.IMAGE
    assert message.media[0].media_type == "image/png"
    assert message.media[0].name == "photo.png"
    assert message.media[0].data == b"png-bytes"
    await plugin.stop()


async def test_receive_carries_a_rejected_attachment_into_the_plugin_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        client.inbound_text = ""
        client.inbound_rejections = [RejectedMedia(kind=MediaKind.VIDEO, reason=MediaRejectionReason.TOO_LARGE)]
        return client

    monkeypatch.setattr(plugin_module.agim, "WeChatClient", factory)
    plugin = WeChatPlugin(_context(MemoryKV()))
    await plugin.start()

    message = await plugin.receive()

    assert message.media == []
    assert len(message.rejected_media) == 1
    assert message.rejected_media[0].kind is ChannelMediaKind.VIDEO
    assert message.rejected_media[0].reason is ChannelMediaRejectionReason.TOO_LARGE
    await plugin.stop()


async def test_send_reuses_stored_context_token(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[FakeClient] = []

    def factory(**kwargs: Any) -> FakeClient:
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(plugin_module.agim, "WeChatClient", factory)
    kv = MemoryKV()
    await kv.set("reply:context:user-1", "context-1")
    plugin = WeChatPlugin(_context(kv))
    await plugin.start()

    await plugin.send("user-1", "reply")

    assert clients[-1].sent == [("user-1", "reply", "context-1")]
    await plugin.stop()


async def test_start_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_module.agim, "WeChatClient", lambda **kwargs: FakeClient(**kwargs))
    plugin = WeChatPlugin(_context(MemoryKV(), config={}))

    with pytest.raises(ValueError):
        await plugin.start()


async def test_send_before_start_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin_module.agim, "WeChatClient", lambda **kwargs: FakeClient(**kwargs))
    plugin = WeChatPlugin(_context(MemoryKV()))

    with pytest.raises(RuntimeError):
        await plugin.send("user-1", "reply")

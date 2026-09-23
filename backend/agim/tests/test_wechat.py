"""Personal WeChat iLink login, receive, send, and normalization."""

import httpx

from agim import LoginHandshake, LoginStatus, WeChatAuthClient, WeChatClient
from agim.wechat.auth import ILINK_BASE_URL
from agim.wechat.client import DEFAULT_LONG_POLL_TIMEOUT_MS, _next_timeout_ms, normalize_message


def test_wechat_messages_are_normalized() -> None:
    text_message = normalize_message(
        {
            "message_id": "msg-1",
            "from_user_id": "user-1",
            "context_token": "context-1",
            "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
        }
    )
    voice_message = normalize_message(
        {
            "message_id": "msg-2",
            "from_user_id": "user-1",
            "item_list": [{"type": 3, "voice_item": {"text": "voice text"}}],
        }
    )

    assert text_message is not None
    assert text_message.text == "hello"
    assert text_message.reply_token == "context-1"
    assert voice_message is not None
    assert voice_message.text == "voice text"


def test_wechat_uses_server_long_poll_timeout_with_bounds() -> None:
    assert _next_timeout_ms({}) == DEFAULT_LONG_POLL_TIMEOUT_MS
    assert _next_timeout_ms({"longpolling_timeout_ms": 12_000}) == 12_000
    assert _next_timeout_ms({"longpolling_timeout_ms": 1_000}) == 5_000
    assert _next_timeout_ms({"longpolling_timeout_ms": 120_000}) == 60_000


async def test_wechat_qr_login_returns_a_persistable_handshake() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/get_bot_qrcode"):
            assert request.url.params["bot_type"] == "3"
            return httpx.Response(
                200,
                json={"qrcode": "qr-1", "qrcode_img_content": "https://weixin.qq.com/qr-1"},
            )
        if request.url.path.endswith("/get_qrcode_status"):
            assert request.url.params["qrcode"] == "qr-1"
            return httpx.Response(
                200,
                json={"status": "confirmed", "bot_token": "token-1", "ilink_bot_id": "bot-1"},
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    auth = WeChatAuthClient(client=client)
    handshake = await auth.create_login()
    state = await auth.poll_login(handshake)

    assert handshake.qr_content == "https://weixin.qq.com/qr-1"
    assert handshake.state == {"qrcode": "qr-1", "base_url": ILINK_BASE_URL}
    assert state.status is LoginStatus.CONNECTED
    assert state.credentials is not None
    assert state.credentials.config["ilink_bot_id"] == "bot-1"
    assert state.credentials.secrets["bot_token"] == "token-1"
    await client.aclose()


async def test_wechat_client_is_stateless_across_receive_and_send() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/getupdates"):
            assert request.content and b"cursor-1" in request.content
            return httpx.Response(
                200,
                json={
                    "ret": 0,
                    "get_updates_buf": "cursor-2",
                    "msgs": [
                        {
                            "message_id": "msg-1",
                            "from_user_id": "user-1",
                            "context_token": "context-1",
                            "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
                        }
                    ],
                },
            )
        return httpx.Response(200, json={"ret": 0})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WeChatClient(token="token-1", base_url="https://ilink.example.invalid", client=http_client)
    result = await client.receive("cursor-1")
    await client.send("user-1", "reply", context_token=result.message.reply_token)

    assert result.message.text == "hello"
    assert result.cursor == "cursor-2"
    assert result.message.reply_token == "context-1"
    assert b'"context_token":"context-1"' in calls[1].content
    await client.aclose()
    await http_client.aclose()


async def test_wechat_client_requires_a_token_for_send() -> None:
    client = WeChatClient(base_url="https://ilink.example.invalid")

    try:
        await client.send("user-1", "reply")
    except RuntimeError as error:
        assert "no bot token" in str(error)
    else:  # pragma: no cover - the assertion above is the contract
        raise AssertionError("send should require a bot token")


def test_login_handshake_round_trips_through_serialization() -> None:
    handshake = LoginHandshake(qr_content="qr", qr_url=None, state={"qrcode": "q", "base_url": "https://x"})
    assert LoginHandshake.model_validate(handshake.model_dump()) == handshake

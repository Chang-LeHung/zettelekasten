"""Personal WeChat iLink login, receive, send, and normalization."""

import base64

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from agim import (
    LoginHandshake,
    LoginStatus,
    MediaKind,
    MediaTooLargeError,
    WeChatAuthClient,
    WeChatClient,
)
from agim.wechat.auth import ILINK_BASE_URL
from agim.wechat.client import DEFAULT_LONG_POLL_TIMEOUT_MS, _next_timeout_ms, normalize_message
from agim.wechat.media import (
    CDN_BASE_URL,
    MediaRef,
    build_cdn_download_url,
    decrypt_aes_ecb,
    fetch_media,
    media_refs,
    parse_aes_key,
)

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"z" * 24
_AES_KEY = bytes(range(16))


def _encrypt(payload: bytes, key: bytes) -> bytes:
    padding = 16 - len(payload) % 16
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(payload + bytes([padding]) * padding) + encryptor.finalize()


def _hex_key(key: bytes) -> str:
    return key.hex()


def _base64_hex_key(key: bytes) -> str:
    return base64.b64encode(key.hex().encode("ascii")).decode("ascii")


def _base64_raw_key(key: bytes) -> str:
    return base64.b64encode(key).decode("ascii")


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


def test_wechat_media_only_messages_keep_a_placeholder() -> None:
    message = normalize_message(
        {
            "message_id": "msg-3",
            "from_user_id": "user-1",
            "item_list": [
                {"type": 2, "image_item": {"media": {"encrypt_query_param": "enc-1", "aes_key": "a2V5"}}},
                {"type": 5, "video_item": {"media": {"encrypt_query_param": "enc-2", "aes_key": "a2V5"}}},
            ],
        }
    )

    assert message is not None
    assert message.text == "[image]\n[video]"
    assert message.media == []


def test_wechat_media_refs_read_every_downloadable_item() -> None:
    refs = media_refs(
        {
            "item_list": [
                {"type": 1, "text_item": {"text": "look"}},
                {
                    "type": 2,
                    "image_item": {
                        "media": {"full_url": "https://cdn.example.invalid/image", "aes_key": "a2V5"},
                        "aeskey": _hex_key(_AES_KEY),
                    },
                },
                {
                    "type": 3,
                    "voice_item": {
                        "encode_type": 6,
                        "media": {"encrypt_query_param": "enc-voice", "aes_key": _base64_hex_key(_AES_KEY)},
                    },
                },
                {
                    "type": 4,
                    "file_item": {
                        "file_name": "report.pdf",
                        "media": {"encrypt_query_param": "enc-file", "aes_key": _base64_hex_key(_AES_KEY)},
                    },
                },
                {"type": 2, "image_item": {"media": {"aes_key": "a2V5"}}},
            ]
        }
    )

    assert [ref.kind.value for ref in refs] == ["image", "voice", "file"]
    assert refs[0].full_url == "https://cdn.example.invalid/image"
    assert refs[0].aes_key == base64.b64encode(_AES_KEY).decode("ascii")
    assert refs[1].media_type == "audio/silk"
    assert refs[2].media_type == "application/pdf"
    assert refs[2].name == "report.pdf"


def test_wechat_aes_keys_accept_both_wire_encodings() -> None:
    assert parse_aes_key(base64.b64encode(_AES_KEY).decode("ascii")) == _AES_KEY
    assert parse_aes_key(_base64_hex_key(_AES_KEY)) == _AES_KEY

    with pytest.raises(ValueError):
        parse_aes_key(base64.b64encode(b"short").decode("ascii"))


def test_wechat_media_decryption_drops_pkcs7_padding() -> None:
    assert decrypt_aes_ecb(_encrypt(_IMAGE_BYTES, _AES_KEY), _AES_KEY) == _IMAGE_BYTES


def test_wechat_cdn_url_is_built_when_the_server_sends_no_full_url() -> None:
    url = build_cdn_download_url("a=b&c", CDN_BASE_URL)

    assert url == f"{CDN_BASE_URL}/download?encrypted_query_param=a%3Db%26c"


async def test_wechat_receive_downloads_and_decrypts_image_media() -> None:
    encrypted = _encrypt(_IMAGE_BYTES, _AES_KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getupdates"):
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
                            "item_list": [
                                {"type": 1, "text_item": {"text": "look at this"}},
                                {
                                    "type": 2,
                                    "image_item": {
                                        "media": {"encrypt_query_param": "enc-1", "aes_key": "a2V5"},
                                        "aeskey": _hex_key(_AES_KEY),
                                    },
                                },
                            ],
                        }
                    ],
                },
            )
        assert request.url.path == "/c2c/download"
        assert request.url.params["encrypted_query_param"] == "enc-1"
        return httpx.Response(200, content=encrypted)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WeChatClient(token="token-1", base_url="https://ilink.example.invalid", client=http_client)

    result = await client.receive()

    assert result.message.text == "look at this\n[image]"
    assert len(result.message.media) == 1
    image = result.message.media[0]
    assert image.kind.value == "image"
    assert image.media_type == "image/png"
    assert image.data == _IMAGE_BYTES
    await client.aclose()
    await http_client.aclose()


async def test_wechat_receive_keeps_the_placeholder_when_media_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getupdates"):
            return httpx.Response(
                200,
                json={
                    "ret": 0,
                    "msgs": [
                        {
                            "message_id": "msg-1",
                            "from_user_id": "user-1",
                            "item_list": [
                                {
                                    "type": 4,
                                    "file_item": {
                                        "file_name": "notes.txt",
                                        "media": {"encrypt_query_param": "enc-1", "aes_key": "bad-key"},
                                    },
                                }
                            ],
                        }
                    ],
                },
            )
        return httpx.Response(404, content=b"missing")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WeChatClient(token="token-1", base_url="https://ilink.example.invalid", client=http_client)

    result = await client.receive()

    assert result.message.text == "[file]"
    assert result.message.media == []
    await client.aclose()
    await http_client.aclose()


def test_wechat_media_refs_are_capped() -> None:
    items = [
        {
            "type": 2,
            "image_item": {
                "media": {
                    "encrypt_query_param": f"enc-{index}",
                    "aes_key": _base64_raw_key(_AES_KEY),
                }
            },
        }
        for index in range(30)
    ]

    refs = media_refs({"item_list": items})

    assert len(refs) == 16


async def test_wechat_receive_never_attaches_more_than_the_item_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getupdates"):
            return httpx.Response(
                200,
                json={
                    "ret": 0,
                    "msgs": [
                        {
                            "message_id": "msg-1",
                            "from_user_id": "user-1",
                            "item_list": [
                                {
                                    "type": 2,
                                    "image_item": {
                                        "media": {
                                            "encrypt_query_param": f"enc-{index}",
                                            "aes_key": _base64_raw_key(_AES_KEY),
                                        }
                                    },
                                }
                                for index in range(30)
                            ],
                        }
                    ],
                },
            )
        return httpx.Response(200, content=_encrypt(_IMAGE_BYTES, _AES_KEY))

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WeChatClient(token="token-1", base_url="https://ilink.example.invalid", client=http_client)

    result = await client.receive()

    assert len(result.message.media) == 16
    await client.aclose()
    await http_client.aclose()


async def test_wechat_media_download_streams_and_refuses_an_oversized_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 64)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ref = MediaRef(kind=MediaKind.IMAGE, media_type="image/png", encrypt_query_param="enc-1")

    with pytest.raises(MediaTooLargeError, match="limit"):
        await fetch_media(http_client, ref, cdn_base_url=CDN_BASE_URL, max_bytes=16)

    await http_client.aclose()


async def test_wechat_media_download_refuses_a_declared_oversized_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 64, headers={"content-length": "64"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ref = MediaRef(kind=MediaKind.IMAGE, media_type="image/png", encrypt_query_param="enc-1")

    with pytest.raises(MediaTooLargeError, match="declares"):
        await fetch_media(http_client, ref, cdn_base_url=CDN_BASE_URL, max_bytes=16)

    await http_client.aclose()


async def test_wechat_receive_reports_an_oversized_attachment_instead_of_dropping_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getupdates"):
            return httpx.Response(
                200,
                json={
                    "ret": 0,
                    "msgs": [
                        {
                            "message_id": "msg-1",
                            "from_user_id": "user-1",
                            "item_list": [
                                {
                                    "type": 2,
                                    "image_item": {
                                        "media": {"encrypt_query_param": "enc-1", "aes_key": _base64_raw_key(_AES_KEY)}
                                    },
                                }
                            ],
                        }
                    ],
                },
            )
        return httpx.Response(200, content=_encrypt(_IMAGE_BYTES, _AES_KEY))

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WeChatClient(
        token="token-1",
        base_url="https://ilink.example.invalid",
        client=http_client,
        media_max_bytes=8,
    )

    result = await client.receive()

    assert result.message.media == []
    assert [item.kind for item in result.message.rejected_media] == [MediaKind.IMAGE]
    assert result.message.rejected_media[0].reason.value == "too_large"
    await client.aclose()
    await http_client.aclose()


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


async def test_wechat_receive_hands_over_every_message_of_one_batch() -> None:
    """A poll that carries a burst must not drop the messages behind the first."""
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if not request.url.path.endswith("/getupdates"):
            return httpx.Response(200, json={"ret": 0})
        polls += 1
        if request.content and b"cursor-2" in request.content:
            return httpx.Response(
                200,
                json={
                    "ret": 0,
                    "get_updates_buf": "cursor-3",
                    "msgs": [
                        {
                            "message_id": "msg-3",
                            "from_user_id": "user-1",
                            "item_list": [{"type": 1, "text_item": {"text": "hello 3"}}],
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "ret": 0,
                "get_updates_buf": "cursor-2",
                "msgs": [
                    {
                        "message_id": f"msg-{index}",
                        "from_user_id": "user-1",
                        "item_list": [{"type": 1, "text_item": {"text": f"hello {index}"}}],
                    }
                    for index in range(3)
                ],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = WeChatClient(token="token-1", base_url="https://ilink.example.invalid", client=http_client)

    first = await client.receive("cursor-1")
    second = await client.receive(first.cursor)
    third = await client.receive(second.cursor)

    assert [result.message.text for result in (first, second, third)] == ["hello 0", "hello 1", "hello 2"]
    # The batch cursor only moves once its last message has been handed over.
    assert first.cursor == "cursor-1"
    assert second.cursor == "cursor-1"
    assert third.cursor == "cursor-2"
    # Nothing left in the batch: the next call polls the server again.
    fourth = await client.receive(third.cursor)
    assert fourth.message.text == "hello 3"
    assert fourth.cursor == "cursor-3"
    assert polls == 2
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

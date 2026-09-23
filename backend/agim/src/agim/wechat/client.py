"""Personal WeChat implementation of the unified agim client."""

import asyncio
import base64
import random
from typing import Any

import httpx

from ..client import IMClient
from ..log import get_logger
from ..models import InboundMessage, LoginHandshake, LoginState, ReceiveResult
from .auth import ILINK_APP_CLIENT_VERSION, ILINK_APP_ID, ILINK_BASE_URL, WeChatAuthClient

DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
MIN_LONG_POLL_TIMEOUT_MS = 5_000
MAX_LONG_POLL_TIMEOUT_MS = 60_000
MIN_EMPTY_RESPONSE_DELAY_SECONDS = 0.25
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_SECONDS = 30.0

logger = get_logger(__name__)


def _headers(token: str) -> dict[str, str]:
    random_uin = str(random.getrandbits(32)).encode()
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {token}",
        "X-WECHAT-UIN": base64.b64encode(random_uin).decode(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }


def _base_info() -> dict[str, str]:
    return {"channel_version": "2.4.9", "bot_agent": "Zett"}


def _next_timeout_ms(payload: dict[str, Any]) -> int:
    """Honor the server's suggested long-poll timeout within safe bounds."""
    suggested = payload.get("longpolling_timeout_ms")
    if not isinstance(suggested, int):
        return DEFAULT_LONG_POLL_TIMEOUT_MS
    return min(MAX_LONG_POLL_TIMEOUT_MS, max(MIN_LONG_POLL_TIMEOUT_MS, suggested))


def _text_from_message(message: dict[str, Any]) -> str | None:
    for item in message.get("item_list") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == 1:
            text = item.get("text_item")
            if isinstance(text, dict) and isinstance(text.get("text"), str):
                return text["text"]
        if item.get("type") == 3:
            voice = item.get("voice_item")
            if isinstance(voice, dict) and isinstance(voice.get("text"), str):
                return voice["text"]
        labels = {2: "[image]", 4: "[file]", 5: "[video]"}
        if item.get("type") in labels:
            return labels[item["type"]]
    return None


def normalize_message(message: dict[str, Any]) -> InboundMessage | None:
    """Normalize one iLink update into the package message model."""
    text = _text_from_message(message)
    if text is None or not text.strip():
        return None
    user_id = message.get("from_user_id")
    event_id = message.get("message_id")
    if not isinstance(user_id, str) or not user_id:
        return None
    if not isinstance(event_id, str) or not event_id:
        event_id = str(message.get("seq") or "")
    if not event_id:
        return None
    context_token = message.get("context_token")
    return InboundMessage(
        event_id=event_id,
        chat_id=user_id,
        user_id=user_id,
        text=text.strip(),
        reply_token=context_token if isinstance(context_token, str) else None,
    )


class WeChatClient(IMClient):
    """Login, long-poll, and send over the Tencent personal WeChat iLink API.

    The client keeps no persistence: the caller stores the login handshake and
    the ``get_updates_buf`` cursor, and passes the reply context token back on
    each ``send``.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = ILINK_BASE_URL,
        client: httpx.AsyncClient | None = None,
        auth: WeChatAuthClient | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None
        self._auth = auth or WeChatAuthClient()

    async def aclose(self) -> None:
        """Close the HTTP clients owned by this instance."""
        await self._auth.aclose()
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def login(self) -> LoginHandshake:
        """Request a QR code and return the handshake the caller must store."""
        return await self._auth.create_login()

    async def is_login(self, handshake: LoginHandshake, *, verify_code: str | None = None) -> LoginState:
        """Poll one stored handshake, optionally with a pairing code."""
        return await self._auth.poll_login(handshake, verify_code=verify_code)

    async def receive(self, cursor: str | None = None) -> ReceiveResult:
        """Long-poll until one normalized inbound message is available."""
        current = cursor or ""
        failures = 0
        long_poll_timeout_ms = DEFAULT_LONG_POLL_TIMEOUT_MS
        while True:
            try:
                response = await self._get_client().post(
                    f"{self._base_url}/ilink/bot/getupdates",
                    json={"get_updates_buf": current, "base_info": _base_info()},
                    headers=_headers(self._require_token()),
                    timeout=(long_poll_timeout_ms / 1000) + 5,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("WeChat getupdates returned an invalid response")
                if payload.get("ret") not in (None, 0) or payload.get("errcode") not in (None, 0):
                    raise RuntimeError(f"WeChat getupdates failed: {payload.get('errmsg') or payload.get('errcode')}")
                next_cursor = payload.get("get_updates_buf")
                if isinstance(next_cursor, str):
                    current = next_cursor
                long_poll_timeout_ms = _next_timeout_ms(payload)
                messages = payload.get("msgs") or []
                for raw in messages:
                    if not isinstance(raw, dict):
                        continue
                    message = normalize_message(raw)
                    if message is not None:
                        return ReceiveResult(message=message, cursor=current)
                failures = 0
                if not messages:
                    # Some gateways return immediately on transient upstream
                    # conditions. A tiny pause prevents a hot getupdates loop.
                    await asyncio.sleep(MIN_EMPTY_RESPONSE_DELAY_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                logger.exception(
                    "WeChat getupdates failed; consecutive_failures=%d max=%d",
                    failures,
                    MAX_CONSECUTIVE_FAILURES,
                )
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    failures = 0
                    await asyncio.sleep(BACKOFF_SECONDS)
                else:
                    await asyncio.sleep(2)

    async def send(self, chat_id: str, text: str, *, context_token: str | None = None) -> None:
        """Send one text message, reusing the caller's stored context token."""
        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": chat_id,
            "client_id": f"agim-{random.getrandbits(64):x}",
            "message_type": 2,
            "message_state": 2,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        }
        if context_token:
            message["context_token"] = context_token
        response = await self._get_client().post(
            f"{self._base_url}/ilink/bot/sendmessage",
            json={"msg": message, "base_info": _base_info()},
            headers=_headers(self._require_token()),
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("ret") not in (None, 0):
            raise RuntimeError(f"WeChat sendmessage failed: {payload.get('errmsg') or payload.get('ret')}")

    def _require_token(self) -> str:
        if not self._token:
            raise RuntimeError("WeChat client has no bot token; complete login first")
        return self._token

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20)
        return self._client


__all__ = [
    "DEFAULT_LONG_POLL_TIMEOUT_MS",
    "MAX_LONG_POLL_TIMEOUT_MS",
    "MIN_LONG_POLL_TIMEOUT_MS",
    "WeChatClient",
    "normalize_message",
]

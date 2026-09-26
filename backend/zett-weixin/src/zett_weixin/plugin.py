"""Personal WeChat channel plugin for Zett, backed by the agim SDK."""

import agim
from zett.plugins import (
    ChannelCredentials,
    ChannelInboundMessage,
    ChannelLoginChallenge,
    ChannelLoginState,
    ChannelLoginStatus,
    ChannelMedia,
    ChannelMediaKind,
    ChannelMediaRejection,
    ChannelMediaRejectionReason,
    ChannelPlugin,
    PluginContext,
)

HANDSHAKE_KEY = "login:handshake"
VERIFY_CODE_KEY = "login:verify_code"
CURSOR_KEY = "receive:cursor"


def _context_key(chat_id: str) -> str:
    return f"reply:context:{chat_id}"


class WeChatPlugin(ChannelPlugin):
    """Login, receive, and send over the Tencent personal WeChat iLink API.

    Zett owns persistence here: the plugin keeps the login handshake, receive
    cursor, and per-conversation reply tokens in ``context.kv`` because agim
    is deliberately stateless.
    """

    plugin_id = "wechat"
    plugin_label = "WeChat"

    def __init__(self, context: PluginContext) -> None:
        self.context = context
        self._login_client: agim.WeChatClient | None = None
        self._client: agim.WeChatClient | None = None

    async def start(self) -> None:
        """Build the runtime client from the stored iLink credentials."""
        base_url = self.context.config.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError("WeChat plugin requires config.base_url")
        token = self.context.secrets.get("bot_token")
        self._client = agim.WeChatClient(
            token=token if isinstance(token, str) and token else None,
            base_url=base_url,
        )

    async def stop(self) -> None:
        """Close both the login-phase and runtime clients."""
        for client in (self._client, self._login_client):
            if client is not None:
                await client.aclose()
        self._client = None
        self._login_client = None

    async def login(self) -> ChannelLoginChallenge:
        """Request a QR code and persist the handshake Zett hands back later."""
        handshake = await self._auth_client().login()
        await self.context.kv.set(HANDSHAKE_KEY, handshake.model_dump(mode="json"))
        await self.context.kv.delete(VERIFY_CODE_KEY)
        return ChannelLoginChallenge(qr_content=handshake.qr_content, qr_url=handshake.qr_url)

    async def submit_login_code(self, code: str) -> None:
        """Persist the pairing code shown by WeChat for the next poll."""
        if not code.strip():
            return
        await self.context.kv.set(VERIFY_CODE_KEY, code)

    async def is_login(self) -> ChannelLoginState:
        """Poll the stored handshake and translate agim's state for Zett."""
        raw = await self.context.kv.get(HANDSHAKE_KEY)
        if not isinstance(raw, dict):
            return ChannelLoginState(
                status=ChannelLoginStatus.EXPIRED,
                message="Login session expired; request a new QR code.",
            )
        try:
            handshake = agim.LoginHandshake.model_validate(raw)
        except ValueError:
            return ChannelLoginState(
                status=ChannelLoginStatus.EXPIRED,
                message="Login session expired; request a new QR code.",
            )
        verify_code = await self.context.kv.get(VERIFY_CODE_KEY)
        state = await self._auth_client().is_login(
            handshake,
            verify_code=verify_code if isinstance(verify_code, str) and verify_code else None,
        )
        credentials = (
            ChannelCredentials(config=state.credentials.config, secrets=state.credentials.secrets)
            if state.credentials is not None
            else None
        )
        return ChannelLoginState(
            status=ChannelLoginStatus(state.status.value),
            message=state.message,
            credentials=credentials,
        )

    async def receive(self) -> ChannelInboundMessage:
        """Await one message and persist the cursor and reply context token."""
        client = self._require_client()
        cursor = await self.context.kv.get(CURSOR_KEY)
        result = await client.receive(cursor if isinstance(cursor, str) else None)
        await self.context.kv.set(CURSOR_KEY, result.cursor)
        if result.message.reply_token:
            await self.context.kv.set(_context_key(result.message.chat_id), result.message.reply_token)
        return ChannelInboundMessage(
            event_id=result.message.event_id,
            chat_id=result.message.chat_id,
            user_id=result.message.user_id,
            text=result.message.text,
            media=[
                ChannelMedia(
                    kind=ChannelMediaKind(item.kind.value),
                    media_type=item.media_type,
                    name=item.name,
                    data=item.data,
                )
                for item in result.message.media
            ],
            rejected_media=[
                ChannelMediaRejection(
                    kind=ChannelMediaKind(item.kind.value),
                    reason=ChannelMediaRejectionReason(item.reason.value),
                )
                for item in result.message.rejected_media
            ],
            reply_token=result.message.reply_token,
        )

    async def send(self, chat_id: str, text: str) -> None:
        """Send one message, reusing the context token stored for the chat."""
        if not chat_id.strip():
            raise ValueError("WeChat chat id cannot be blank")
        if not text.strip():
            raise ValueError("WeChat message cannot be blank")
        client = self._require_client()
        context_token = await self.context.kv.get(_context_key(chat_id))
        await client.send(
            chat_id,
            text,
            context_token=context_token if isinstance(context_token, str) and context_token else None,
        )

    def _auth_client(self) -> agim.WeChatClient:
        if self._login_client is None:
            self._login_client = agim.WeChatClient()
        return self._login_client

    def _require_client(self) -> agim.WeChatClient:
        if self._client is None:
            raise RuntimeError("WeChat plugin is not started")
        return self._client


__all__ = ["WeChatPlugin"]

"""Use-case orchestration for IM login, channels, and conversations.

Platform work lives in plugins registered through Zett's plugin mechanism
(``zett.channels`` entry points, for example ``zett-weixin``). This service
owns everything host side: which channels exist, how a login becomes a channel
record, how inbound messages become Agent turns, and where the replies go.
"""

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage
from zett_agent import new_uuid7

from ..._compat import UTC
from ...infra.log import get_logger
from ...infra.plugins import PluginRegistry, ZettKVStorage, build_registry
from ...plugins import (
    MAX_CHANNEL_MEDIA_BYTES,
    MAX_CHANNEL_MEDIA_ITEMS,
    MAX_CHANNEL_MEDIA_TOTAL_BYTES,
    ChannelInboundMessage,
    ChannelLoginChallenge,
    ChannelLoginState,
    ChannelMedia,
    ChannelPlugin,
    KVStorage,
    PluginError,
    PluginLoadError,
)
from ...schemas import (
    Channel,
    ChannelLogin,
    ChannelLoginStart,
    ChannelLoginStatus,
    ChannelPluginInfo,
    ChannelType,
    ChannelUpdate,
)
from .agent import AgentClient, AgentEventKind, AgentTurnRequest, ZettIMAgentClient
from .store import ChannelDraft, ChannelRuntime, ChannelStore

logger = get_logger(__name__)

LOGIN_TTL = timedelta(minutes=5)
RECEIVE_RETRY_SECONDS = 2.0

#: Chat locks are cheap but a busy process talks to unbounded chats, so keep a bounded cache.
LOCK_CACHE_LIMIT = 256

#: One failed turn must not look like an ignored message to the person waiting.
TURN_FAILURE_REPLY = "Sorry, something went wrong while handling that message. Please try again."

#: An attachment nobody can carry must reach the sender as a plain answer.
MEDIA_TOO_LARGE_REPLY = "That file is too large to process. Please send a smaller one."


def _qr_data_url(value: str) -> str:
    image = qrcode.make(value, image_factory=SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


@dataclass(frozen=True, slots=True)
class _BoundedMedia:
    """The attachments one inbound message may contribute to a turn."""

    kept: list[ChannelMedia]
    #: Whether anything was left out because it was too large to carry.
    too_large: bool


def _bounded_media(media: list[ChannelMedia], *, channel_id: str) -> _BoundedMedia:
    """Keep only the attachments Zett accepts from an untrusted plugin.

    A plugin owns the objects it returns, so it can bypass the contract model's
    field validation by constructing them unvalidated. The count, per-item, and
    total limits are therefore enforced again on this side of the boundary.
    An attachment dropped for size is reported so the sender hears why.
    """
    kept: list[ChannelMedia] = []
    total = 0
    too_large = False
    for item in media:
        size = len(item.data) if isinstance(item.data, bytes) else 0
        if not size:
            logger.warning("Inbound attachment carries no payload; channel_id=%s kind=%s", channel_id, item.kind)
            continue
        if len(kept) >= MAX_CHANNEL_MEDIA_ITEMS:
            logger.warning(
                "Inbound message carries more than %d attachments; dropping the rest; channel_id=%s",
                MAX_CHANNEL_MEDIA_ITEMS,
                channel_id,
            )
            break
        if size > MAX_CHANNEL_MEDIA_BYTES:
            logger.warning(
                "Inbound attachment is over the per-item limit; channel_id=%s kind=%s bytes=%d",
                channel_id,
                item.kind,
                size,
            )
            too_large = True
            continue
        if total + size > MAX_CHANNEL_MEDIA_TOTAL_BYTES:
            logger.warning(
                "Inbound message exceeds the media budget; dropping attachments; channel_id=%s bytes=%d",
                channel_id,
                size,
            )
            too_large = True
            continue
        kept.append(item)
        total += size
    return _BoundedMedia(kept=kept, too_large=too_large)


@dataclass(slots=True)
class _ChannelRunner:
    """One running channel plugin plus its inbound receive loop."""

    plugin: ChannelPlugin
    task: asyncio.Task[None]


class ChannelService:
    """Own the plugin registry, running channels, and Agent bridge."""

    def __init__(
        self,
        *,
        registry: PluginRegistry | None = None,
        kv: KVStorage | None = None,
        agent: AgentClient | None = None,
    ) -> None:
        self._kv = kv or ZettKVStorage()
        self._store = ChannelStore(self._kv)
        self._registry = registry or build_registry()
        self._agent = agent or ZettIMAgentClient()
        self._runners: dict[str, _ChannelRunner] = {}
        self._logins: dict[str, ChannelPlugin] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def initialize(self) -> None:
        """Start a receive loop for every enabled channel."""
        plugin_ids = self._registry.ids()
        if plugin_ids:
            logger.info("Channel plugins available: %s", ", ".join(plugin_ids))
        else:
            logger.warning("No channel plugins are installed; channel APIs will report failures")
        await self.reload()

    async def shutdown(self) -> None:
        """Stop every receive loop and close every plugin."""
        for channel_id in list(self._runners):
            await self._stop_runner(channel_id)
        for login_id, plugin in list(self._logins.items()):
            await self._safe_stop(plugin, scope=f"login:{login_id}")
        self._logins.clear()

    async def reload(self) -> None:
        """Reconcile running plugins with the persisted enabled channels."""
        runtimes = {runtime.channel.id: runtime for runtime in await self._store.list_runtime_channels()}
        for channel_id in set(self._runners) - set(runtimes):
            await self._stop_runner(channel_id)
        for channel_id, runtime in runtimes.items():
            if channel_id not in self._runners:
                await self._start_runner(runtime)

    async def list_channels(self) -> list[Channel]:
        """List configured channels."""
        return await self._store.list_channels()

    async def update_channel(self, channel_id: str, payload: ChannelUpdate) -> Channel:
        """Update channel policy and restart its receive loop."""
        if not channel_id.strip():
            raise KeyError("Channel id cannot be blank")
        existing = await self._store.get_channel(channel_id)
        updated = await self._store.update_channel(channel_id, payload)
        # Provider, reasoning, and coding policy are read per turn, so only the
        # enabled flag needs a new plugin instance. Restarting for a policy edit
        # would cancel the turn that is running right now and drop its reply.
        if existing is not None and existing.enabled == updated.enabled:
            return updated
        await self._stop_runner(channel_id)
        if updated.enabled:
            runtime = await self._store.get_runtime_channel(channel_id)
            if runtime is None:
                return updated
            await self._start_runner(runtime)
        return updated

    async def delete_channel(self, channel_id: str) -> bool:
        """Stop one channel and remove its record, markers, and bindings."""
        if not channel_id.strip():
            return False
        await self._stop_runner(channel_id)
        return await self._store.delete_channel(channel_id)

    async def provider_referenced(self, provider_id: str) -> bool:
        """Return whether any channel routes turns through the provider."""
        return any(channel.provider_id == provider_id for channel in await self.list_channels())

    async def list_plugins(self) -> list[ChannelPluginInfo]:
        """List the channel plugins installed in this process."""
        return [
            ChannelPluginInfo(channel_type=descriptor.plugin_id, label=descriptor.label)
            for descriptor in self._registry.describe()
        ]

    async def start_login(self, payload: ChannelLoginStart) -> ChannelLogin:
        """Start one QR flow through the plugin registered for its channel type."""
        if not payload.provider_id.strip():
            raise ValueError("Channel login requires a provider id")
        channel_type = self._resolve_channel_type(payload.channel_type)
        login_id = new_uuid7()
        try:
            plugin = self._registry.create(channel_type, scope_id=login_id, kv=self._kv)
        except (PluginLoadError, KeyError) as error:
            raise PluginError(f"Channel plugin unavailable: {channel_type}") from error
        try:
            challenge = ChannelLoginChallenge.model_validate(await plugin.login())
        except Exception as error:
            logger.exception("Channel plugin login failed; login_id=%s", login_id)
            await self._safe_stop(plugin, scope=f"login:{login_id}")
            raise PluginError("Channel plugin failed to start login") from error
        now = datetime.now(UTC)
        login = ChannelLogin(
            id=login_id,
            channel_type=channel_type,
            provider_id=payload.provider_id,
            name=payload.name,
            status=ChannelLoginStatus.PENDING,
            qr_url=challenge.qr_url,
            qr_data_url=_qr_data_url(challenge.qr_content),
            message="Scan the QR code to finish signing in.",
            expires_at=now + LOGIN_TTL,
            created_at=now,
            updated_at=now,
        )
        await self._store.save_login(login, state={})
        self._logins[login_id] = plugin
        return login

    def _resolve_channel_type(self, requested: str | None) -> str:
        """Return the requested platform, or the only installed one.

        Raises:
            ValueError: when no platform was requested and the installed set is
                not exactly one plugin, so the caller cannot be guessed at.
        """
        available = self._registry.ids()
        if requested is not None and requested.strip():
            if requested not in available:
                raise ValueError(f"Unknown channel plugin: {requested}")
            return requested
        if len(available) == 1:
            return available[0]
        if not available:
            raise ValueError("No channel plugins are installed")
        raise ValueError("channel_type is required when multiple channel plugins are installed")

    async def poll_login(self, login_id: str, *, verify_code: str | None = None) -> ChannelLogin | None:
        """Poll one QR flow and create its channel after authorization."""
        if not login_id.strip():
            return None
        stored = await self._store.get_login(login_id)
        if stored is None:
            return None
        login, _state = stored
        if login.status not in {
            ChannelLoginStatus.PENDING,
            ChannelLoginStatus.SCANNED,
            ChannelLoginStatus.VERIFY_REQUIRED,
        }:
            return login
        if login.expires_at <= datetime.now(UTC):
            return await self._fail_login(login, ChannelLoginStatus.EXPIRED, "QR code expired; request a new one.")
        plugin = self._logins.get(login_id)
        if plugin is None:
            return await self._fail_login(
                login, ChannelLoginStatus.EXPIRED, "Login session expired; request a new QR code."
            )
        if verify_code:
            await self._submit_login_code(plugin, verify_code, login_id)
        try:
            state = ChannelLoginState.model_validate(await plugin.is_login())
        except Exception as error:
            logger.exception("IM login poll failed; login_id=%s", login_id)
            return await self._fail_login(login, ChannelLoginStatus.FAILED, str(error))
        if state.status is not ChannelLoginStatus.CONNECTED:
            if state.status in {ChannelLoginStatus.FAILED, ChannelLoginStatus.EXPIRED}:
                return await self._fail_login(login, state.status, state.message)
            return await self._finish_login(login, status=state.status, message=state.message)
        if state.credentials is None:
            return await self._fail_login(
                login, ChannelLoginStatus.FAILED, "Login succeeded but the plugin returned no credentials."
            )
        if not state.credentials.secrets:
            return await self._fail_login(
                login, ChannelLoginStatus.FAILED, "Login succeeded but the plugin returned no secrets."
            )
        channel = await self._store.create_channel(
            ChannelDraft(
                name=login.name or _default_channel_name(login.channel_type),
                channel_type=login.channel_type,
                provider_id=login.provider_id,
                config=state.credentials.config,
                secrets=state.credentials.secrets,
            )
        )
        connected = await self._finish_login(
            login,
            status=ChannelLoginStatus.CONNECTED,
            message=state.message,
            channel_id=channel.id,
        )
        await self._discard_login(login_id)
        try:
            await self.reload()
        except Exception:
            # The channel is persisted; a restart is preferable to duplicating it.
            logger.exception("IM channel reload failed after login; channel_id=%s", channel.id)
        return connected

    async def send_message(self, channel_id: str, chat_id: str, text: str) -> None:
        """Deliver one proactive message through a running channel."""
        if not channel_id.strip() or not chat_id.strip():
            raise ValueError("Channel and chat id cannot be blank")
        if not text.strip():
            raise ValueError("Channel message cannot be blank")
        runner = self._runners.get(channel_id)
        if runner is None:
            raise KeyError(f"Active channel not found: {channel_id}")
        try:
            await runner.plugin.send(chat_id, text)
        except Exception as error:
            logger.exception("Channel plugin send failed; channel_id=%s", channel_id)
            raise PluginError("Channel plugin failed to send the message") from error

    async def _finish_login(
        self,
        login: ChannelLogin,
        *,
        status: ChannelLoginStatus,
        message: str,
        channel_id: str | None = None,
    ) -> ChannelLogin:
        updated = login.model_copy(
            update={
                "status": status,
                "message": message,
                "channel_id": channel_id or login.channel_id,
                "updated_at": datetime.now(UTC),
            }
        )
        await self._store.save_login(updated, state={})
        return updated

    async def _fail_login(self, login: ChannelLogin, status: ChannelLoginStatus, message: str) -> ChannelLogin:
        """Finish one login that produced no channel and release its plugin."""
        finished = await self._finish_login(login, status=status, message=message)
        await self._discard_login(login.id)
        return finished

    async def _discard_login(self, login_id: str) -> None:
        """Stop and forget the plugin of a login flow that will not poll again.

        A plugin kept here owns an HTTP client, so leaving an expired or failed
        login in the map leaks one client per abandoned QR flow.
        """
        plugin = self._logins.pop(login_id, None)
        if plugin is not None:
            await self._safe_stop(plugin, scope=f"login:{login_id}")

    async def _start_runner(self, runtime: ChannelRuntime) -> None:
        """Start one channel plugin, skipping the channel if the plugin fails.

        A broken plugin must not abort startup or block the other channels, so
        construction and ``start`` failures are logged and swallowed here.
        """
        channel_id = runtime.channel.id
        plugin: ChannelPlugin | None = None
        try:
            plugin = self._registry.create(
                runtime.channel.channel_type,
                scope_id=channel_id,
                kv=self._kv,
                config=runtime.config,
                secrets=runtime.secrets,
            )
            await plugin.start()
        except Exception:
            logger.exception("Channel plugin failed to start; channel_id=%s", channel_id)
            if plugin is not None:
                await self._safe_stop(plugin, scope=f"channel:{channel_id}")
            return
        task = asyncio.create_task(self._consume(channel_id, plugin), name=f"im-channel:{channel_id}")
        self._runners[channel_id] = _ChannelRunner(plugin=plugin, task=task)

    async def _stop_runner(self, channel_id: str) -> None:
        runner = self._runners.pop(channel_id, None)
        if runner is None:
            return
        runner.task.cancel()
        await asyncio.gather(runner.task, return_exceptions=True)
        await self._safe_stop(runner.plugin, scope=f"channel:{channel_id}")

    async def _safe_stop(self, plugin: ChannelPlugin, *, scope: str) -> None:
        """Close one plugin without letting its failure escape the boundary."""
        try:
            await plugin.stop()
        except Exception:
            logger.exception("Channel plugin failed to stop; scope=%s", scope)

    async def _submit_login_code(self, plugin: ChannelPlugin, code: str, login_id: str) -> None:
        """Forward a pairing code, keeping a plugin failure from failing the poll."""
        try:
            await plugin.submit_login_code(code)
        except Exception:
            logger.exception("Channel plugin rejected the login code; login_id=%s", login_id)

    async def _consume(self, channel_id: str, plugin: ChannelPlugin) -> None:
        """Pull inbound messages forever and answer them through the Agent."""
        while True:
            try:
                message = ChannelInboundMessage.model_validate(await plugin.receive())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("IM receive failed; channel_id=%s", channel_id)
                await asyncio.sleep(RECEIVE_RETRY_SECONDS)
                continue
            if not message.text.strip() and not message.media and not message.rejected_media:
                continue
            try:
                reply = await self._handle_message(channel_id, message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("IM turn failed; channel_id=%s event_id=%s", channel_id, message.event_id)
                reply = TURN_FAILURE_REPLY
            if reply is None or not reply.strip():
                continue
            try:
                await plugin.send(message.chat_id, reply)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("IM reply failed; channel_id=%s event_id=%s", channel_id, message.event_id)

    async def _handle_message(self, channel_id: str, message: ChannelInboundMessage) -> str | None:
        """Run one deduplicated, serialized Agent turn for an inbound message."""
        runtime = await self._store.get_runtime_channel(channel_id)
        if runtime is None:
            raise KeyError(f"Enabled channel not found: {channel_id}")
        if not await self._store.claim_event(channel_id, message.event_id):
            return None
        bounded = _bounded_media(message.media, channel_id=channel_id)
        if message.rejected_media or bounded.too_large:
            # An oversized attachment is answered directly: the model never sees
            # a turn whose media was dropped, and the sender is told why.
            return MEDIA_TOO_LARGE_REPLY
        # The same external conversation may be active in multiple processes, so
        # serialize turns per channel+chat pair.
        lock = self._lock_for(channel_id, message.chat_id)
        async with lock:
            return await self._run_turn(runtime, message, media=bounded.kept)

    def _lock_for(self, channel_id: str, chat_id: str) -> asyncio.Lock:
        """Return the chat's lock, keeping the cache bounded by dropping idle entries.

        A held lock is never dropped, so an in-flight turn and anything queued
        behind it keep serialization; only chats with no active turn are evicted.
        """
        key = (channel_id, chat_id)
        lock = self._locks.get(key)
        if lock is None:
            if len(self._locks) >= LOCK_CACHE_LIMIT:
                for existing_key, existing_lock in list(self._locks.items()):
                    if existing_key != key and not existing_lock.locked():
                        self._locks.pop(existing_key, None)
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def _run_turn(
        self,
        runtime: ChannelRuntime,
        message: ChannelInboundMessage,
        *,
        media: list[ChannelMedia],
    ) -> str:
        """Run one serialized Agent turn for an external conversation."""
        channel_id = runtime.channel.id
        agent_session_id = await self._store.agent_session_for(channel_id, message.chat_id)
        request = AgentTurnRequest(
            request_id=message.event_id,
            provider_id=runtime.channel.provider_id,
            agent_session_id=agent_session_id,
            message=message.text,
            media=media,
            reasoning_effort=runtime.channel.reasoning_effort,
            allow_coding=runtime.channel.allow_coding,
            metadata={
                "source": "im",
                "channel_id": channel_id,
                "channel_name": runtime.channel.name,
                "channel_type": runtime.channel.channel_type,
                "external_chat_id": message.chat_id,
                "external_user_id": message.user_id,
            },
        )
        final_content: str | None = None
        session_id: str | None = None
        async for event in self._agent.stream_turn(request):
            if event.session_id:
                session_id = event.session_id
                await self._store.bind_agent_session(channel_id, message.chat_id, event.session_id)
            if event.type is AgentEventKind.DELTA and event.content:
                final_content = f"{final_content or ''}{event.content}"
            elif event.type is AgentEventKind.COMPLETED:
                final_content = event.content or final_content
            elif event.type is AgentEventKind.FAILED:
                raise RuntimeError(event.error or "Agent turn failed")
        if final_content is None:
            raise RuntimeError("Agent turn ended without a response")
        if session_id is None:
            raise RuntimeError("Agent turn ended without a session ID")
        return final_content


def _default_channel_name(channel_type: ChannelType) -> str:
    return f"{channel_type} bot"


channel_service = ChannelService()

__all__ = ["ChannelService", "channel_service"]

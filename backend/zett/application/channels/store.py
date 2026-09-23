"""KV-backed persistence for channels, logins, and routing state.

Channel records, login sessions, message-dedup markers, and Agent session
bindings are few and tiny, so they live in the shared key-value store instead
of dedicated SQLAlchemy tables. All keys use the ``im:`` namespace.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...infra.security import decrypt_secret, encrypt_secret
from ...plugins import JsonValue, KVStorage
from ...schemas import Channel, ChannelLogin, ChannelType, ChannelUpdate

CHANNEL_PREFIX = "im:channel:"
LOGIN_PREFIX = "im:login:"
EVENT_PREFIX = "im:event:"
SESSION_PREFIX = "im:session:"


class ChannelDraft(BaseModel):
    """Write model for a channel account created by a successful login."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    channel_type: ChannelType
    provider_id: str = Field(min_length=1, max_length=36)
    enabled: bool = True
    reasoning_effort: str = Field(default="medium", pattern="^(off|low|medium|high)$")
    allow_coding: bool = False
    config: dict[str, JsonValue] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class ChannelRuntime(BaseModel):
    """Enabled channel plus decrypted credentials needed by its plugin."""

    channel: Channel
    config: dict[str, JsonValue]
    secrets: dict[str, str]


class ChannelStore:
    """Store channel bookkeeping under ``im:`` keys in a ``KVStorage``."""

    def __init__(self, kv: KVStorage) -> None:
        self._kv = kv

    async def create_channel(self, draft: ChannelDraft) -> Channel:
        """Create one channel account and encrypt its secrets."""
        if not draft.name.strip():
            raise ValueError("Channel name cannot be blank")
        if not draft.provider_id.strip():
            raise ValueError("Channel provider id cannot be blank")
        now = datetime.now(UTC)
        channel = Channel(
            id=str(uuid.uuid7()),
            name=draft.name,
            channel_type=draft.channel_type,
            provider_id=draft.provider_id,
            enabled=draft.enabled,
            reasoning_effort=draft.reasoning_effort,
            allow_coding=draft.allow_coding,
            config=draft.config,
            secret_keys=sorted(draft.secrets),
            created_at=now,
            updated_at=now,
        )
        await self._write(channel, draft.secrets)
        return channel

    async def list_channels(self) -> list[Channel]:
        """Return channels sorted by display name."""
        records = await self._kv.iter_prefix(CHANNEL_PREFIX)
        channels = [Channel.model_validate(payload["channel"]) for _, payload in records]
        return sorted(channels, key=lambda channel: (channel.name.lower(), channel.id))

    async def get_channel(self, channel_id: str) -> Channel | None:
        """Return one public channel model."""
        if not channel_id.strip():
            return None
        payload = await self._kv.get(f"{CHANNEL_PREFIX}{channel_id}")
        return Channel.model_validate(payload["channel"]) if payload is not None else None

    async def update_channel(self, channel_id: str, payload: ChannelUpdate) -> Channel:
        """Apply a partial update while preserving platform credentials."""
        if not channel_id.strip():
            raise KeyError("Channel id cannot be blank")
        stored = await self._read(channel_id)
        if stored is None:
            raise KeyError(f"Channel not found: {channel_id}")
        channel, secrets = stored
        updated = channel.model_copy(
            update={
                "name": payload.name or channel.name,
                "provider_id": payload.provider_id or channel.provider_id,
                "enabled": channel.enabled if payload.enabled is None else payload.enabled,
                "reasoning_effort": payload.reasoning_effort or channel.reasoning_effort,
                "allow_coding": channel.allow_coding if payload.allow_coding is None else payload.allow_coding,
                "updated_at": datetime.now(UTC),
            }
        )
        await self._write(updated, secrets)
        return updated

    async def delete_channel(self, channel_id: str) -> bool:
        """Delete one channel with its dedup markers and session bindings."""
        if not channel_id.strip():
            return False
        if await self._kv.get(f"{CHANNEL_PREFIX}{channel_id}") is None:
            return False
        await self._kv.delete(f"{CHANNEL_PREFIX}{channel_id}")
        await self._delete_prefix(f"{EVENT_PREFIX}{channel_id}:")
        await self._delete_prefix(f"{SESSION_PREFIX}{channel_id}:")
        return True

    async def list_runtime_channels(self) -> list[ChannelRuntime]:
        """Return enabled channels with decrypted plugin credentials."""
        runtimes: list[ChannelRuntime] = []
        for channel in await self.list_channels():
            if not channel.enabled:
                continue
            stored = await self._read(channel.id)
            if stored is None:
                continue
            record, secrets = stored
            runtimes.append(ChannelRuntime(channel=record, config=record.config, secrets=secrets))
        return runtimes

    async def get_runtime_channel(self, channel_id: str) -> ChannelRuntime | None:
        """Return one enabled channel with decrypted plugin credentials."""
        if not channel_id.strip():
            return None
        stored = await self._read(channel_id)
        if stored is None:
            return None
        channel, secrets = stored
        if not channel.enabled:
            return None
        return ChannelRuntime(channel=channel, config=channel.config, secrets=secrets)

    async def save_login(self, login: ChannelLogin, *, state: dict[str, JsonValue]) -> None:
        """Persist one QR login session and its provider continuation state."""
        if not login.id.strip():
            raise ValueError("Channel login id cannot be blank")
        await self._kv.set(
            f"{LOGIN_PREFIX}{login.id}",
            {"login": login.model_dump(mode="json"), "state": state},
        )

    async def get_login(self, login_id: str) -> tuple[ChannelLogin, dict[str, JsonValue]] | None:
        """Return one stored login session with its provider state."""
        if not login_id.strip():
            return None
        payload = await self._kv.get(f"{LOGIN_PREFIX}{login_id}")
        if payload is None:
            return None
        return ChannelLogin.model_validate(payload["login"]), dict(payload.get("state") or {})

    async def claim_event(self, channel_id: str, event_id: str) -> bool:
        """Return ``True`` the first time an inbound event is seen."""
        if not channel_id.strip() or not event_id.strip():
            return False
        key = f"{EVENT_PREFIX}{channel_id}:{event_id}"
        if await self._kv.get(key) is not None:
            return False
        await self._kv.set(key, datetime.now(UTC).isoformat())
        return True

    async def agent_session_for(self, channel_id: str, chat_id: str) -> str | None:
        """Return the Agent session bound to one external conversation."""
        if not channel_id.strip() or not chat_id.strip():
            return None
        value = await self._kv.get(f"{SESSION_PREFIX}{channel_id}:{chat_id}")
        return value if isinstance(value, str) else None

    async def bind_agent_session(self, channel_id: str, chat_id: str, session_id: str) -> None:
        """Bind one external conversation to its Agent session."""
        if not channel_id.strip() or not chat_id.strip() or not session_id.strip():
            return
        await self._kv.set(f"{SESSION_PREFIX}{channel_id}:{chat_id}", session_id)

    async def _read(self, channel_id: str) -> tuple[Channel, dict[str, str]] | None:
        payload = await self._kv.get(f"{CHANNEL_PREFIX}{channel_id}")
        if payload is None:
            return None
        channel = Channel.model_validate(payload["channel"])
        ciphertext = payload.get("secrets")
        plaintext = decrypt_secret(ciphertext if isinstance(ciphertext, str) else None)
        secrets: dict[str, Any] = json.loads(plaintext) if plaintext else {}
        return channel, {key: str(value) for key, value in secrets.items()}

    async def _write(self, channel: Channel, secrets: dict[str, str]) -> None:
        serialized = json.dumps(secrets, ensure_ascii=False, separators=(",", ":"))
        await self._kv.set(
            f"{CHANNEL_PREFIX}{channel.id}",
            {"channel": channel.model_dump(mode="json"), "secrets": encrypt_secret(serialized)},
        )

    async def _delete_prefix(self, prefix: str) -> None:
        for key, _ in await self._kv.iter_prefix(prefix):
            await self._kv.delete(key)


__all__ = ["ChannelDraft", "ChannelRuntime", "ChannelStore"]

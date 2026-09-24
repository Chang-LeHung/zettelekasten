"""Per-session UI preferences backed by the versioned application KV store."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...infra.persistence.dao import KeyValueStorage, key_value_storage
from ...schemas import ProviderConnection, ProviderType

SESSION_MODEL_KEY_PREFIX = "sessions.model."


class SessionModelPreference(BaseModel):
    """The provider configuration most recently used by one conversation."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    provider: ProviderType
    model: str


class SessionModelPreferenceService:
    """Remember and restore model selection without extending Agent session rows."""

    def __init__(self, storage: KeyValueStorage = key_value_storage) -> None:
        self._storage = storage

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{SESSION_MODEL_KEY_PREFIX}{session_id}"

    async def get(self, session_id: str) -> SessionModelPreference | None:
        """Return the last model used by a session, if it has completed selection."""
        record = await self._storage.get(self._key(session_id))
        return None if record is None else SessionModelPreference.model_validate(record.value)

    async def remember(self, session_id: str, connection: ProviderConnection) -> SessionModelPreference:
        """Update the preference after an enabled provider has been resolved."""
        preference = SessionModelPreference(
            provider_id=connection.id,
            provider=connection.provider,
            model=connection.model,
        )
        await self._storage.update(self._key(session_id), preference.model_dump(mode="json"))
        return preference

    async def delete(self, session_id: str) -> bool:
        """Remove every preference revision owned by one deleted session."""
        return await self._storage.delete(self._key(session_id))

    async def provider_referenced(self, provider_id: str) -> bool:
        """Return whether any session still prefers the provider."""
        records = await self._storage.iter_prefix(SESSION_MODEL_KEY_PREFIX)
        return any(SessionModelPreference.model_validate(record.value).provider_id == provider_id for record in records)


session_model_preference_service = SessionModelPreferenceService()

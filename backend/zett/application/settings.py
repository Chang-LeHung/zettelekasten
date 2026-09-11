"""Typed application settings backed by the local versioned key-value store."""

from pydantic import BaseModel, ConfigDict, Field

from ..infra.dao import KeyValueStorage, key_value_storage

RUNTIME_SETTINGS_KEY = "settings.runtime"


class RuntimeSettings(BaseModel):
    """User-configurable limits applied without restarting the service."""

    model_config = ConfigDict(extra="forbid")

    max_message_images: int = Field(
        default=32,
        ge=1,
        le=256,
        description="Maximum number of pasted images accepted in one user message",
    )


class RuntimeSettingsService:
    """Load and replace the complete runtime configuration as one atomic value."""

    def __init__(self, storage: KeyValueStorage = key_value_storage) -> None:
        self._storage = storage

    def get(self) -> RuntimeSettings:
        """Return persisted settings, or schema defaults before the first update."""
        record = self._storage.get(RUNTIME_SETTINGS_KEY)
        return RuntimeSettings() if record is None else RuntimeSettings.model_validate(record.value)

    def update(self, value: RuntimeSettings) -> RuntimeSettings:
        """Atomically replace all runtime settings and return the stored value."""
        stored = value.model_copy(deep=True)
        self._storage.set(RUNTIME_SETTINGS_KEY, stored.model_dump(mode="json"))
        return stored


runtime_settings_service = RuntimeSettingsService()

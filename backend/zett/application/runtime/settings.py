"""Typed application settings backed by the local versioned key-value store."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...config import settings
from ...infra.persistence.dao import KeyValueStorage, key_value_storage

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
    max_turn_iterations: int = Field(
        default=128,
        ge=1,
        le=256,
        description="Maximum number of primary model calls allowed for one turn",
    )
    max_asset_size_bytes: int = Field(
        default=settings.max_asset_size_bytes,
        ge=1,
        le=2 * 1024**3,
        description="Maximum bytes accepted for one asset or message-image collection",
    )
    compaction_max_tokens: int = Field(
        default=800_000,
        ge=128_000,
        le=800_000,
        description="Estimated active-context tokens that trigger compaction",
    )
    compaction_keep_recent_tokens: int = Field(
        default=64_000,
        ge=32_000,
        le=256_000,
        description="Recent estimated tokens retained after compaction",
    )

    @model_validator(mode="after")
    def validate_compaction_window(self) -> RuntimeSettings:
        """Keep a non-empty budget for the generated compact snapshot."""
        if self.compaction_keep_recent_tokens >= self.compaction_max_tokens:
            raise ValueError("compaction_keep_recent_tokens must be below compaction_max_tokens")
        return self


class RuntimeSettingsService:
    """Load and replace the complete runtime configuration as one atomic value."""

    def __init__(self, storage: KeyValueStorage = key_value_storage) -> None:
        self._storage = storage

    async def get(self) -> RuntimeSettings:
        """Return persisted settings, or schema defaults before the first update."""
        record = await self._storage.get(RUNTIME_SETTINGS_KEY)
        return RuntimeSettings() if record is None else RuntimeSettings.model_validate(record.value)

    async def update(self, value: RuntimeSettings) -> RuntimeSettings:
        """Atomically replace all runtime settings and return the stored value."""
        stored = value.model_copy(deep=True)
        await self._storage.update(RUNTIME_SETTINGS_KEY, stored.model_dump(mode="json"))
        return stored


runtime_settings_service = RuntimeSettingsService()

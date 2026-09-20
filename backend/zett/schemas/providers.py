"""Write and read models for model provider connections."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProviderType(StrEnum):
    """Provider protocols understood by the future model adapter layer."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"
    RESPONSES_COMPATIBLE = "responses_compatible"


class ProviderWrite(BaseModel):
    """Complete provider configuration accepted by the storage boundary."""

    name: str = Field(min_length=1, max_length=100, description="User-facing configuration name")
    provider: ProviderType = Field(description="Provider protocol used by the model adapter")
    model: str = Field(min_length=1, max_length=200, description="Provider model identifier")
    base_url: str | None = Field(default=None, description="Optional API endpoint override")
    api_key: str | None = Field(
        default=None,
        min_length=1,
        repr=False,
        exclude=True,
        description="Write-only API key encrypted before persistence",
    )
    enabled: bool = Field(default=True, description="Whether this configuration may be selected")
    metadata: dict[str, object] = Field(default_factory=dict, description="Provider-specific JSON options")


class ProviderEntity(BaseModel):
    """Safe provider metadata returned without its API key or ciphertext."""

    id: str = Field(description="Stable provider configuration UUID")
    name: str
    provider: ProviderType
    model: str
    base_url: str | None = None
    api_key_configured: bool = Field(description="Whether an encrypted API key is stored")
    enabled: bool
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProviderConnection(BaseModel):
    """Decrypted configuration consumed transiently by a model adapter."""

    model_config = ConfigDict(frozen=True)

    id: str
    provider: ProviderType
    model: str
    base_url: str | None = None
    api_key: SecretStr | None = Field(default=None, repr=False)
    metadata: dict[str, object] = Field(default_factory=dict)

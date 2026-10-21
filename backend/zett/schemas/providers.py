"""Write and read models for model provider connections."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from .._compat import Self, StrEnum


class ProviderType(StrEnum):
    """Provider protocols understood by the future model adapter layer."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"
    RESPONSES_COMPATIBLE = "responses_compatible"
    ANTHROPIC_COMPATIBLE = "anthropic_compatible"


#: Provider-side tool types are short identifiers such as ``web_search_20250305``.
WEB_SEARCH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,99}$")

_ANTHROPIC_PROTOCOLS = frozenset({ProviderType.ANTHROPIC, ProviderType.ANTHROPIC_COMPATIBLE})
#: Protocols whose adapter sends hosted tools on both Chat Completions and the Responses API.
_OPENAI_STYLE = frozenset(
    {
        ProviderType.OPENAI,
        ProviderType.OPENAI_COMPATIBLE,
        ProviderType.RESPONSES_COMPATIBLE,
        ProviderType.DEEPSEEK,
    }
)


def supports_images(metadata: dict[str, object]) -> bool:
    """Return whether a provider's model reads images; an unset flag means it does.

    Providers saved before the flag existed keep the behaviour they had, which
    offered image reading.
    """
    return metadata.get("multimodal", True) is not False


def is_deepseek_model(model: str) -> bool:
    """Return whether one model id names a DeepSeek model, whatever endpoint serves it."""
    return "deepseek" in model.lower()


def default_web_search_name(provider: ProviderType, model: str, *, response: bool) -> str | None:
    """Return the provider-side web search tool type a configuration uses by default.

    ``None`` means the protocol has no search tool this application knows, so a
    caller has to name one explicitly (a gateway may document its own) or the
    configuration cannot search. The names are the tools' wire types: OpenAI and
    its compatible services call it ``web_search`` on either API, Anthropic
    versions it (``web_search_20260318``), DeepSeek's Anthropic endpoint answers
    the older ``web_search_20250305``, and Gemini grounds with ``google_search``.
    """
    if provider in _ANTHROPIC_PROTOCOLS:
        return "web_search_20250305" if is_deepseek_model(model) else "web_search_20260318"
    if provider == ProviderType.GOOGLE:
        return "google_search"
    if provider in _OPENAI_STYLE:
        return "web_search"
    return None


def web_search_hint(provider: ProviderType, model: str, *, response: bool) -> str:
    """Describe what a search answer holds for this protocol, for the settings form.

    The text differs by protocol because the results do too: Anthropic returns
    page titles and links with the page text encrypted, OpenAI returns search
    call metadata, and DeepSeek answers through Anthropic's shape.
    """
    name = default_web_search_name(provider, model, response=response)
    if name is None:
        return "This endpoint has no search tool Zett knows; type the search tool name your service documents."
    if provider in _ANTHROPIC_PROTOCOLS:
        if is_deepseek_model(model):
            return (
                "DeepSeek flash models search through the Anthropic API with web_search_20250305. "
                "Results come back as page titles and links."
            )
        return (
            "Anthropic searches with web_search_20260318 and returns page titles and links. "
            "Page text stays on the provider, so a snippet may be missing."
        )
    if provider == ProviderType.GOOGLE:
        return "Gemini grounds with google_search and returns the queries it ran plus the pages it cited."
    if response:
        return "The Responses API searches with web_search and returns the queries it ran plus the cited pages."
    return "Chat Completions searches with web_search when the service supports a hosted search tool."


def web_search_error(provider: ProviderType, model: str, *, response: bool, name: str | None) -> str | None:
    """Explain why a configuration cannot enable web search, or return ``None``.

    DeepSeek is the one vendor whose search depends on the endpoint: only its
    flash models search, and only through the Anthropic Messages API. Its chat
    and Responses endpoints accept the tool and then answer from memory, which is
    worse than refusing, so that combination is rejected before it is stored.
    """
    if name is not None and not WEB_SEARCH_NAME_PATTERN.fullmatch(name):
        return "Web search tool name may only use letters, digits, '_', '.', ':' and '-' (100 characters at most)"
    if provider == ProviderType.OLLAMA:
        return "Ollama has no hosted web search"
    if is_deepseek_model(model):
        if provider not in _ANTHROPIC_PROTOCOLS:
            return "DeepSeek models search the web only through the Anthropic API"
        if "flash" not in model.lower():
            return "Only DeepSeek flash models support web search on the Anthropic API"
    if name is None and default_web_search_name(provider, model, response=response) is None:
        return "Web search needs a service that hosts one; for this endpoint type the search tool name instead"
    return None


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

    @model_validator(mode="after")
    def web_search_must_be_supported(self) -> Self:
        """Reject a search toggle that the selected protocol or model cannot honour."""
        enabled = self.metadata.get("web_search", False)
        name = self.metadata.get("web_search_name")
        if not isinstance(enabled, bool):
            raise ValueError("web_search must be a boolean")
        if name is not None and not isinstance(name, str):
            raise ValueError("web_search_name must be a string")
        if not enabled:
            return self
        response = self.metadata.get("response", False) is True
        error = web_search_error(self.provider, self.model, response=response, name=name or None)
        if error is not None:
            raise ValueError(error)
        return self


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


class ProviderChoice(BaseModel):
    """One enabled provider a model-facing tool may reference by ID.

    Tools return this projection instead of the whole entity so a prompt never
    carries provider configuration that scheduling does not need.
    """

    id: str = Field(description="Stable provider configuration UUID")
    name: str = Field(description="User-facing configuration name")
    provider: ProviderType = Field(description="Provider protocol used by the model adapter")
    model: str = Field(description="Provider model identifier")


class ProviderConnection(BaseModel):
    """Decrypted configuration consumed transiently by a model adapter."""

    model_config = ConfigDict(frozen=True)

    id: str
    provider: ProviderType
    model: str
    base_url: str | None = None
    api_key: SecretStr | None = Field(default=None, repr=False)
    metadata: dict[str, object] = Field(default_factory=dict)

"""Build zett-agent provider adapters from encrypted application settings."""

from zett_agent.model import (
    AgentModel,
)
from zett_agent.providers.anthropic import (
    AnthropicProvider,
)
from zett_agent.providers.deepseek import (
    DeepSeekProvider,
)
from zett_agent.providers.google import (
    GoogleProvider,
)
from zett_agent.providers.ollama import (
    OllamaProvider,
)
from zett_agent.providers.openai import (
    OpenAIProvider,
)

from .._compat import TypeAliasType
from ..schemas import ProviderConnection, ProviderType

ProviderAdapter = TypeAliasType(
    "ProviderAdapter", AnthropicProvider | DeepSeekProvider | GoogleProvider | OllamaProvider | OpenAIProvider
)


def anthropic_base_url(value: str | None) -> str | None:
    """Return the API root the Anthropic SDK expects, or ``None`` for its default.

    The SDK appends ``/v1/messages`` itself, so an address pasted with more than
    the root (``…/v1`` as OpenAI-style endpoints are written, or the full
    ``…/v1/messages`` that many Anthropic-compatible services document and that
    people copy whole) would be requested at ``/v1/v1/messages`` or
    ``/v1/messages/v1/messages`` and fail with a bare 404. Trailing slashes, a
    trailing ``/messages``, and one trailing ``/v1`` are dropped.
    """
    if not value:
        return None
    root = value.strip().rstrip("/")
    for suffix in ("/messages", "/v1"):
        if root.endswith(suffix):
            root = root[: -len(suffix)].rstrip("/")
    return root or None


def uses_responses_api(model: AgentModel | None) -> bool:
    """Return whether one adapter speaks the Responses API.

    Only the OpenAI-style adapters implement that protocol, and only when they
    were built with ``response=True``: the Anthropic, Google, and Ollama adapters
    reject that flag at construction because their protocols cannot serve it. The
    attribute therefore identifies the protocol without importing every adapter.
    """
    return bool(getattr(model, "response", False))


def create_model(
    connection: ProviderConnection,
) -> ProviderAdapter:
    """Create one caller-owned asynchronous provider adapter."""
    api_key = connection.api_key.get_secret_value() if connection.api_key is not None else ""
    temperature_value = connection.metadata.get("temperature")
    temperature = float(temperature_value) if isinstance(temperature_value, int | float) else None
    response_value = connection.metadata.get("response", False)
    response = response_value if isinstance(response_value, bool) else False
    match connection.provider:
        case ProviderType.OPENAI | ProviderType.OPENAI_COMPATIBLE:
            return OpenAIProvider(
                model=connection.model,
                api_key=api_key,
                base_url=connection.base_url,
                temperature=temperature,
                response=response,
            )
        case ProviderType.RESPONSES_COMPATIBLE:
            if not connection.base_url:
                raise ValueError("Responses-compatible providers require a base URL")
            return OpenAIProvider(
                model=connection.model,
                api_key=api_key,
                base_url=connection.base_url,
                temperature=temperature,
                response=True,
            )
        case ProviderType.DEEPSEEK:
            return DeepSeekProvider(
                model=connection.model,
                api_key=api_key,
                base_url=connection.base_url,
                temperature=temperature,
                response=response,
            )
        case ProviderType.ANTHROPIC | ProviderType.ANTHROPIC_COMPATIBLE:
            if connection.provider == ProviderType.ANTHROPIC_COMPATIBLE and not connection.base_url:
                raise ValueError("Anthropic-compatible providers require a base URL")
            base_url = anthropic_base_url(connection.base_url)
            return AnthropicProvider(
                model=connection.model,
                api_key=api_key,
                **({"base_url": base_url} if base_url else {}),
                response=False,
            )
        case ProviderType.GOOGLE:
            return GoogleProvider(model=connection.model, api_key=api_key, response=response)
        case ProviderType.OLLAMA:
            return OllamaProvider(
                model=connection.model,
                **({"base_url": connection.base_url} if connection.base_url else {}),
                response=response,
            )

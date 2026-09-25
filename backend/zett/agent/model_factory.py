"""Build zett-agent provider adapters from encrypted application settings."""

from zett_agent import (
    AgentModel,
    AnthropicProvider,
    DeepSeekProvider,
    GoogleProvider,
    OllamaProvider,
    OpenAIProvider,
)

from .._compat import TypeAliasType
from ..schemas import ProviderConnection, ProviderType

ProviderAdapter = TypeAliasType(
    "ProviderAdapter", AnthropicProvider | DeepSeekProvider | GoogleProvider | OllamaProvider | OpenAIProvider
)


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
        case ProviderType.ANTHROPIC:
            return AnthropicProvider(
                model=connection.model,
                api_key=api_key,
                **({"base_url": connection.base_url} if connection.base_url else {}),
                response=response,
            )
        case ProviderType.GOOGLE:
            return GoogleProvider(model=connection.model, api_key=api_key, response=response)
        case ProviderType.OLLAMA:
            return OllamaProvider(
                model=connection.model,
                **({"base_url": connection.base_url} if connection.base_url else {}),
                response=response,
            )

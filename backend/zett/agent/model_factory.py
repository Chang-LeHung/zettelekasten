"""Build zett-agent provider adapters from encrypted application settings."""

from zett_agent import (
    AnthropicProvider,
    DeepSeekProvider,
    GoogleProvider,
    OllamaProvider,
    OpenAIProvider,
)

from ..schemas import ProviderConnection, ProviderType

type ProviderAdapter = AnthropicProvider | DeepSeekProvider | GoogleProvider | OllamaProvider | OpenAIProvider


def create_model(
    connection: ProviderConnection,
) -> ProviderAdapter:
    """Create one caller-owned asynchronous provider adapter."""
    api_key = connection.api_key.get_secret_value() if connection.api_key is not None else ""
    temperature_value = connection.metadata.get("temperature")
    temperature = float(temperature_value) if isinstance(temperature_value, int | float) else None
    match connection.provider:
        case ProviderType.OPENAI | ProviderType.OPENAI_COMPATIBLE:
            return OpenAIProvider(
                model=connection.model,
                api_key=api_key,
                base_url=connection.base_url,
                temperature=temperature,
            )
        case ProviderType.DEEPSEEK:
            return DeepSeekProvider(
                model=connection.model,
                api_key=api_key,
                base_url=connection.base_url,
                temperature=temperature,
            )
        case ProviderType.ANTHROPIC:
            return AnthropicProvider(
                model=connection.model,
                api_key=api_key,
                **({"base_url": connection.base_url} if connection.base_url else {}),
            )
        case ProviderType.GOOGLE:
            return GoogleProvider(model=connection.model, api_key=api_key)
        case ProviderType.OLLAMA:
            return OllamaProvider(
                model=connection.model,
                **({"base_url": connection.base_url} if connection.base_url else {}),
            )

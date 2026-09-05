"""Construct native SDK adapters from detached provider configurations."""

from fastapi import HTTPException
from kcs_agent import AgentModel, AnthropicProvider, DeepSeekProvider, GoogleProvider, OllamaProvider, OpenAIProvider

from ..models import AIProviderRuntime
from .provider_dao import ai_provider_storage


def create_agent_model(provider_id: int | None = None) -> tuple[AIProviderRuntime, AgentModel]:
    """Resolve credentials without leaking ORM objects or storing per-run reasoning settings."""
    settings = ai_provider_storage.resolve_connection(provider_id)
    if settings is None or not settings.enabled:
        raise HTTPException(400, "Enable and configure an AI provider first")
    runtime = AIProviderRuntime(provider=settings.provider, model=settings.model)
    key = settings.api_key.get_secret_value() if settings.api_key is not None else ""
    match settings.provider.lower():
        case "openai" | "openai-compatible" | "deepseek":
            deepseek = (
                settings.provider.lower() == "deepseek"
                or "deepseek.com" in (settings.base_url or "").lower()
                or settings.model.lower().startswith("deepseek-")
            )
            adapter = DeepSeekProvider if deepseek else OpenAIProvider
            return runtime, adapter(
                model=settings.model,
                api_key=key,
                base_url=settings.base_url or None,
                temperature=settings.temperature,
            )
        case "anthropic":
            return runtime, AnthropicProvider(
                model=settings.model,
                api_key=key,
                base_url=settings.base_url or "https://api.anthropic.com",
            )
        case "gemini" | "google":
            return runtime, GoogleProvider(model=settings.model, api_key=key)
        case "ollama":
            return runtime, OllamaProvider(model=settings.model, base_url=settings.base_url or "http://localhost:11434")
        case _:
            raise HTTPException(400, f"Unsupported provider: {runtime.provider}")


async def close_agent_model(model: AgentModel) -> None:
    """Release owned clients; injected doubles need only the stream protocol."""
    close = getattr(model, "aclose", None)
    if close is not None:
        await close()

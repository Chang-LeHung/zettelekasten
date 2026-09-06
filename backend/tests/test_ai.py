import pytest
from fastapi import HTTPException
from zett_agent import AgentModel, DeepSeekProvider, ModelRequest, ReasoningEffort

from zett.infra.provider_adapter import create_agent_model
from zett.infra.provider_dao import ai_provider_storage
from zett.models import AIProviderRuntime
from zett.schemas import AIProviderIn


@pytest.mark.parametrize(
    ("provider_name", "expected_model_class", "base_url", "api_key"),
    [
        ("openai-compatible", "OpenAIProvider", None, "test-key"),
        ("anthropic", "AnthropicProvider", None, "test-key"),
        ("gemini", "GoogleProvider", None, "test-key"),
        ("ollama", "OllamaProvider", "http://127.0.0.1:11434", None),
    ],
)
def test_create_agent_model_returns_session_independent_runtime(
    provider_name: str,
    expected_model_class: str,
    base_url: str | None,
    api_key: str | None,
) -> None:
    """Provider construction must not return an ORM object tied to a closed session."""
    provider = ai_provider_storage.create(
        AIProviderIn(
            name=f"{provider_name} test",
            provider=provider_name,
            model="test-model",
            base_url=base_url,
            api_key=api_key,
            temperature=0.2,
            enabled=True,
        )
    )

    runtime, model = create_agent_model(provider.id)

    assert runtime == AIProviderRuntime(provider=provider_name, model="test-model")
    assert isinstance(model, AgentModel)
    assert type(model).__name__ == expected_model_class


def test_create_agent_model_rejects_disabled_provider() -> None:
    provider = ai_provider_storage.create(
        AIProviderIn(
            name="Disabled provider",
            provider="openai-compatible",
            model="test-model",
            api_key="test-key",
            enabled=False,
        )
    )

    with pytest.raises(HTTPException, match="Enable and configure an AI provider first") as error:
        create_agent_model(provider.id)
    assert error.value.status_code == 400


def test_deepseek_compatible_configuration_uses_native_adapter() -> None:
    provider = ai_provider_storage.create(
        AIProviderIn(
            name="DeepSeek",
            provider="openai-compatible",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            api_key="test-key",
            enabled=True,
        )
    )
    _, model = create_agent_model(provider.id)
    assert isinstance(model, DeepSeekProvider)
    assert str(model._client.base_url) == "https://api.deepseek.com"
    assert model._provider_specific_request_extra_fields(
        ModelRequest(messages=(), reasoning_effort=ReasoningEffort.HIGH)
    ) == {"thinking": {"type": "enabled"}}
    assert model._provider_specific_request_extra_fields(
        ModelRequest(messages=(), reasoning_effort=ReasoningEffort.OFF)
    ) == {"thinking": {"type": "disabled"}}

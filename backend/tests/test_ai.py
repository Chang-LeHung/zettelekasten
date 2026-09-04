import pytest
from fastapi import HTTPException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI

from kcs.infra.provider_adapter import DeepSeekChatModel, create_chat_model
from kcs.infra.provider_dao import ai_provider_storage
from kcs.models import AIProviderRuntime
from kcs.schemas import AIProviderIn, ReasoningEffort


@pytest.mark.parametrize(
    ("provider_name", "expected_model_class", "base_url", "api_key"),
    [
        ("openai-compatible", "ChatOpenAI", None, "test-key"),
        ("anthropic", "ChatAnthropic", None, "test-key"),
        ("gemini", "ChatGoogleGenerativeAI", None, "test-key"),
        ("ollama", "ChatOllama", "http://127.0.0.1:11434", None),
    ],
)
def test_create_chat_model_returns_session_independent_runtime(
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

    runtime, model = create_chat_model(provider.id)

    assert runtime == AIProviderRuntime(provider=provider_name, model="test-model")
    assert isinstance(model, BaseChatModel)
    assert type(model).__name__ == expected_model_class


def test_create_chat_model_rejects_disabled_provider() -> None:
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
        create_chat_model(provider.id)
    assert error.value.status_code == 400


def test_openai_compatible_model_receives_selected_reasoning_effort() -> None:
    provider = ai_provider_storage.create(
        AIProviderIn(
            name="Reasoning provider",
            provider="openai-compatible",
            model="reasoning-model",
            api_key="test-key",
            enabled=True,
        )
    )

    _, high_model = create_chat_model(provider.id, ReasoningEffort.HIGH)
    _, off_model = create_chat_model(provider.id, ReasoningEffort.OFF)

    assert isinstance(high_model, ChatOpenAI)
    assert isinstance(off_model, ChatOpenAI)
    assert high_model.reasoning_effort == "high"
    assert off_model.reasoning_effort is None


def test_deepseek_model_preserves_streamed_reasoning_content() -> None:
    provider = ai_provider_storage.create(
        AIProviderIn(
            name="DeepSeek reasoning provider",
            provider="openai-compatible",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            api_key="test-key",
            enabled=True,
        )
    )

    _, model = create_chat_model(provider.id, ReasoningEffort.HIGH)

    assert isinstance(model, DeepSeekChatModel)
    assert model.extra_body == {"thinking": {"type": "enabled"}}
    generation = model._convert_chunk_to_generation_chunk(
        {"choices": [{"delta": {"role": "assistant", "content": "", "reasoning_content": "Think."}}]},
        AIMessageChunk,
        None,
    )
    assert generation is not None
    assert generation.message.additional_kwargs["reasoning_content"] == "Think."

    payload = model._get_request_payload(
        [AIMessage(content="Answer.", additional_kwargs={"reasoning_content": "Think."})]
    )
    assert payload["messages"][0]["reasoning_content"] == "Think."

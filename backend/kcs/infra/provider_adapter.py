from typing import Any

from fastapi import HTTPException
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from ..models import AIProviderRuntime
from ..schemas import ReasoningEffort
from .provider_dao import ai_provider_storage


class DeepSeekChatModel(ChatOpenAI):
    """Preserve DeepSeek thinking fields omitted by LangChain's OpenAI converter."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type[BaseMessageChunk],
        base_generation_info: dict[str, Any] | None,
    ) -> ChatGenerationChunk | None:
        generation = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if generation is None or not isinstance(generation.message, AIMessageChunk):
            return generation
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        delta = choices[0].get("delta") if choices else None
        if isinstance(delta, dict):
            reasoning_content = delta.get("reasoning_content")
            if isinstance(reasoning_content, str) and reasoning_content:
                generation.message.additional_kwargs["reasoning_content"] = reasoning_content
        return generation

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        serialized_messages = payload.get("messages")
        if not isinstance(serialized_messages, list):
            return payload
        for source, serialized in zip(messages, serialized_messages, strict=False):
            if not isinstance(source, AIMessage) or not isinstance(serialized, dict):
                continue
            reasoning_content = source.additional_kwargs.get("reasoning_content")
            if isinstance(reasoning_content, str) and reasoning_content:
                serialized["reasoning_content"] = reasoning_content
        return payload


def create_chat_model(
    provider_id: int | None = None,
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
) -> tuple[AIProviderRuntime, BaseChatModel]:
    """Construct a streaming LangChain model from a detached provider configuration."""
    settings = ai_provider_storage.resolve_connection(provider_id)
    if settings is None or not settings.enabled:
        raise HTTPException(400, "Enable and configure an AI provider first")
    provider = settings.provider.lower()
    runtime = AIProviderRuntime(provider=settings.provider, model=settings.model)

    if provider in ("openai", "openai-compatible", "deepseek"):
        is_deepseek = (
            provider == "deepseek"
            or "deepseek.com" in (settings.base_url or "").lower()
            or settings.model.lower().startswith("deepseek-")
        )
        model_class = DeepSeekChatModel if is_deepseek else ChatOpenAI
        return runtime, model_class(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url or None,
            temperature=settings.temperature,
            streaming=True,
            reasoning_effort=None if reasoning_effort == ReasoningEffort.OFF else reasoning_effort.value,
            extra_body={"thinking": {"type": "disabled" if reasoning_effort == ReasoningEffort.OFF else "enabled"}}
            if is_deepseek
            else None,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if settings.api_key is not None:
            return runtime, ChatAnthropic(
                model_name=settings.model,
                api_key=settings.api_key,
                temperature=settings.temperature,
                timeout=None,
                stop=None,
                streaming=True,
            )
        return runtime, ChatAnthropic(
            model_name=settings.model,
            temperature=settings.temperature,
            timeout=None,
            stop=None,
            streaming=True,
        )
    if provider in ("gemini", "google"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return runtime, ChatGoogleGenerativeAI(
            model=settings.model,
            api_key=settings.api_key,
            temperature=settings.temperature,
            streaming=True,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return runtime, ChatOllama(
            model=settings.model,
            base_url=settings.base_url or "http://localhost:11434",
            temperature=settings.temperature,
        )
    raise HTTPException(400, f"Unsupported provider: {runtime.provider}")

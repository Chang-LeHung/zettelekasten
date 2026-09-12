"""Provider-configuration mapping into zett-agent model adapters."""

from pydantic import SecretStr

from zett.agent.model_factory import create_model
from zett.schemas import ProviderConnection, ProviderType


async def test_model_factory_enables_responses_api_from_provider_metadata() -> None:
    connection = ProviderConnection(
        id="provider-1",
        provider=ProviderType.DEEPSEEK,
        model="deepseek-v4-flash",
        api_key=SecretStr("secret"),
        metadata={"temperature": 0.4, "response": True},
    )

    model = create_model(connection)
    try:
        assert model.response is True
        assert model.temperature == 0.4
        assert str(model._client.base_url) == "https://api.deepseek.com"
    finally:
        await model.aclose()


async def test_model_factory_defaults_to_provider_chat_api() -> None:
    connection = ProviderConnection(
        id="provider-1",
        provider=ProviderType.OPENAI,
        model="gpt-4o",
        api_key=SecretStr("secret"),
    )

    model = create_model(connection)
    try:
        assert model.response is False
    finally:
        await model.aclose()

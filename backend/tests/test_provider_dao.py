import pytest
from fastapi import HTTPException

from zett.infra.provider_dao import AIProviderConnection, ai_provider_storage
from zett.models import AIProviderListOptions
from zett.schemas import AIProviderIn, AIProviderOut


def _provider(name: str, *, enabled: bool = True) -> AIProviderIn:
    return AIProviderIn(
        name=name,
        provider="openai-compatible",
        model="deepseek-v4-flash",
        base_url="https://example.invalid/v1",
        api_key="secret-key",
        enabled=enabled,
    )


def test_provider_storage_crud_returns_pydantic_models() -> None:
    created = ai_provider_storage.create(_provider("Primary"))

    assert isinstance(created, AIProviderOut)
    assert created.api_key_configured is True
    assert ai_provider_storage.get(created.id) == created

    updated = ai_provider_storage.update(created.id, _provider("Renamed", enabled=False))
    assert isinstance(updated, AIProviderOut)
    assert updated.name == "Renamed"
    assert updated.enabled is False
    assert ai_provider_storage.delete(created.id) is True
    assert ai_provider_storage.get(created.id) is None


def test_provider_storage_filters_and_resolves_detached_credentials() -> None:
    first = ai_provider_storage.create(_provider("DeepSeek Primary"))
    ai_provider_storage.create(_provider("Disabled", enabled=False))

    providers = ai_provider_storage.list(AIProviderListOptions(query="deepseek", enabled=True))
    connection = ai_provider_storage.resolve_connection(first.id)

    assert [provider.id for provider in providers] == [first.id]
    assert isinstance(connection, AIProviderConnection)
    assert connection.api_key is not None
    assert connection.api_key.get_secret_value() == "secret-key"


def test_provider_storage_update_rejects_unknown_id() -> None:
    with pytest.raises(HTTPException, match="AI provider not found") as error:
        ai_provider_storage.update(999, _provider("Missing"))
    assert error.value.status_code == 404

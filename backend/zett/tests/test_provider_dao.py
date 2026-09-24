"""Encrypted provider storage behavior on an isolated SQLite database."""

import stat
import sys
from uuid import UUID

import pytest

from zett.config import settings
from zett.infra.persistence.dao.provider import provider_storage
from zett.infra.persistence.database import session_scope
from zett.infra.persistence.storage import AsyncStorage
from zett.infra.persistence.tables import ProviderRow
from zett.schemas import ProviderListOptions, ProviderWrite


def provider(**changes) -> ProviderWrite:
    """Build one complete write model with explicit test credentials."""
    values = {
        "name": "Primary DeepSeek",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "api_key": "test-secret-key",
        "metadata": {"reasoning": True},
    }
    values.update(changes)
    return ProviderWrite(**values)


async def test_provider_crud_encrypts_credentials_and_returns_safe_models():
    created = await provider_storage.create(provider())
    assert isinstance(provider_storage, AsyncStorage)
    assert UUID(created.id).version == 7
    assert created.api_key_configured is True
    assert not hasattr(created, "api_key")
    assert "test-secret-key" not in repr(created)

    async with session_scope() as session:
        row = await session.get(ProviderRow, created.id)
        assert row is not None
        assert row.encrypted_api_key != "test-secret-key"
        assert "test-secret-key" not in row.encrypted_api_key

    connection = await provider_storage.resolve_connection(created.id)
    assert connection is not None
    assert connection.api_key is not None
    assert connection.api_key.get_secret_value() == "test-secret-key"
    assert connection.metadata == {"reasoning": True}
    if sys.platform != "win32":
        # Owner-only permissions are a POSIX promise; Windows keeps its own ACLs.
        assert stat.S_IMODE(settings.provider_key_path.stat().st_mode) == 0o600

    updated = await provider_storage.update(
        created.id,
        provider(name="Local model", provider="ollama", model="qwen3", base_url=None, api_key=None),
    )
    assert updated.id == created.id
    assert updated.provider == "ollama"
    assert updated.api_key_configured is False
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    refreshed = await provider_storage.resolve_connection(created.id)
    assert refreshed is not None and refreshed.api_key is None
    assert await provider_storage.delete(created.id)
    assert await provider_storage.get(created.id) is None
    assert not await provider_storage.delete(created.id)


async def test_provider_queries_filter_before_pagination_and_choose_enabled_default():
    disabled = await provider_storage.create(provider(name="A disabled", enabled=False))
    first = await provider_storage.create(provider(name="B enabled", model="deepseek-reasoner"))
    second = await provider_storage.create(provider(name="C enabled", provider="openai", model="gpt-test"))

    enabled = await provider_storage.list(ProviderListOptions(enabled=True))
    assert [item.id for item in enabled] == [first.id, second.id]
    by_provider = await provider_storage.list(ProviderListOptions(providers=("openai",)))
    assert [item.id for item in by_provider] == [second.id]
    by_query = await provider_storage.list(ProviderListOptions(query="reasoner"))
    assert [item.id for item in by_query] == [first.id]
    paged = await provider_storage.list(ProviderListOptions(enabled=True, limit=1, offset=1))
    assert [item.id for item in paged] == [second.id]
    default = await provider_storage.resolve_connection()
    assert default is not None and default.id == first.id
    assert await provider_storage.resolve_connection(disabled.id) is None
    assert await provider_storage.list(ProviderListOptions(offset=100)) == []


async def test_provider_missing_and_corrupt_credentials_fail_predictably():
    assert await provider_storage.get("missing") is None
    assert await provider_storage.resolve_connection("missing") is None
    with pytest.raises(KeyError, match="Provider not found"):
        await provider_storage.update("missing", provider())

    created = await provider_storage.create(provider())
    async with session_scope() as session:
        row = await session.get(ProviderRow, created.id)
        assert row is not None
        row.encrypted_api_key = "not-a-fernet-token"
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        await provider_storage.resolve_connection(created.id)


def test_provider_write_hides_api_key_from_repr_and_json():
    payload = provider()
    assert "test-secret-key" not in repr(payload)
    assert payload.model_dump() == {
        "name": "Primary DeepSeek",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "enabled": True,
        "metadata": {"reasoning": True},
    }


async def test_responses_compatible_provider_round_trips_through_integer_code():
    created = await provider_storage.create(
        provider(provider="responses_compatible", base_url="https://responses.example/v1")
    )

    assert created.provider == "responses_compatible"
    async with session_scope() as session:
        row = await session.get(ProviderRow, created.id)
        assert row is not None
        assert row.provider == 7
    resolved = await provider_storage.resolve_connection(created.id)
    assert resolved is not None and resolved.provider == "responses_compatible"

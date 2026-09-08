"""Encrypted provider storage behavior on an isolated SQLite database."""

import stat
from uuid import UUID

import pytest

from zett.config import settings
from zett.infra.dao.provider import provider_storage
from zett.infra.database import session_scope
from zett.infra.models import ProviderModel
from zett.infra.storage import Storage
from zett.models import ProviderListOptions
from zett.schemas import ProviderWrite


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


def test_provider_crud_encrypts_credentials_and_returns_safe_models():
    created = provider_storage.create(provider())
    assert isinstance(provider_storage, Storage)
    assert UUID(created.id).version == 7
    assert created.api_key_configured is True
    assert not hasattr(created, "api_key")
    assert "test-secret-key" not in repr(created)

    with session_scope() as session:
        row = session.get(ProviderModel, created.id)
        assert row is not None
        assert row.encrypted_api_key != "test-secret-key"
        assert "test-secret-key" not in row.encrypted_api_key

    connection = provider_storage.resolve_connection(created.id)
    assert connection is not None
    assert connection.api_key is not None
    assert connection.api_key.get_secret_value() == "test-secret-key"
    assert connection.metadata == {"reasoning": True}
    assert stat.S_IMODE(settings.provider_key_path.stat().st_mode) == 0o600

    updated = provider_storage.update(
        created.id,
        provider(name="Local model", provider="ollama", model="qwen3", base_url=None, api_key=None),
    )
    assert updated.id == created.id
    assert updated.provider == "ollama"
    assert updated.api_key_configured is False
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert provider_storage.resolve_connection(created.id).api_key is None
    assert provider_storage.delete(created.id)
    assert provider_storage.get(created.id) is None
    assert not provider_storage.delete(created.id)


def test_provider_queries_filter_before_pagination_and_choose_enabled_default():
    disabled = provider_storage.create(provider(name="A disabled", enabled=False))
    first = provider_storage.create(provider(name="B enabled", model="deepseek-reasoner"))
    second = provider_storage.create(provider(name="C enabled", provider="openai", model="gpt-test"))

    assert [item.id for item in provider_storage.list(ProviderListOptions(enabled=True))] == [first.id, second.id]
    assert [item.id for item in provider_storage.list(ProviderListOptions(providers=("openai",)))] == [second.id]
    assert [item.id for item in provider_storage.list(ProviderListOptions(query="reasoner"))] == [first.id]
    assert [item.id for item in provider_storage.list(ProviderListOptions(enabled=True, limit=1, offset=1))] == [
        second.id
    ]
    assert provider_storage.resolve_connection().id == first.id
    assert provider_storage.resolve_connection(disabled.id) is None
    assert provider_storage.list(ProviderListOptions(offset=100)) == []


def test_provider_missing_and_corrupt_credentials_fail_predictably():
    assert provider_storage.get("missing") is None
    assert provider_storage.resolve_connection("missing") is None
    with pytest.raises(KeyError, match="Provider not found"):
        provider_storage.update("missing", provider())

    created = provider_storage.create(provider())
    with session_scope() as session:
        row = session.get(ProviderModel, created.id)
        assert row is not None
        row.encrypted_api_key = "not-a-fernet-token"
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        provider_storage.resolve_connection(created.id)


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

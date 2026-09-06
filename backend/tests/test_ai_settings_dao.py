from zett.infra.ai_settings_dao import ai_settings_storage
from zett.infra.storage import Storage
from zett.schemas import AISettingsIn, AISettingsOut


def _settings(model: str = "deepseek-v4-flash") -> AISettingsIn:
    return AISettingsIn(
        provider="openai-compatible",
        model=model,
        base_url="https://example.invalid/v1",
        api_key="secret-key",
        temperature=0.2,
        enabled=True,
    )


def test_ai_settings_storage_returns_safe_pydantic_models() -> None:
    assert isinstance(ai_settings_storage, Storage)

    created = ai_settings_storage.create(_settings())
    loaded = ai_settings_storage.get(created.id)

    assert isinstance(created, AISettingsOut)
    assert loaded == created
    assert created.api_key_masked == "configured"
    assert "secret-key" not in created.model_dump_json()


def test_ai_settings_storage_supports_update_list_and_delete() -> None:
    created = ai_settings_storage.create(_settings())

    updated = ai_settings_storage.update(created.id, _settings("deepseek-chat"))

    assert updated.model == "deepseek-chat"
    assert ai_settings_storage.list() == [updated]
    assert ai_settings_storage.delete(created.id) is True
    assert ai_settings_storage.get(created.id) is None

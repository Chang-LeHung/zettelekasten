from datetime import UTC, datetime

from ..schemas import AISettingsIn, AISettingsOut
from .database import session_scope
from .models import AISettingsModel
from .provider_dao import encrypt_api_key
from .storage import EmptyListOptions, Storage


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive timestamps to explicit UTC values."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_output(model: AISettingsModel) -> AISettingsOut:
    """Detach safe singleton settings from their SQLAlchemy session."""
    return AISettingsOut(
        id=model.id,
        provider=model.provider,
        model=model.model,
        base_url=model.base_url,
        temperature=model.temperature,
        enabled=model.enabled,
        updated_at=_as_utc(model.updated_at),
        api_key_masked="configured" if model.encrypted_api_key else "not configured",
    )


class AISettingsStorage(Storage[AISettingsIn, AISettingsOut, int, EmptyListOptions]):
    """SQLAlchemy storage adapter for the legacy singleton AI settings record."""

    def create(self, entity: AISettingsIn) -> AISettingsOut:
        return self._save(1, entity)

    def get(self, entity_id: int) -> AISettingsOut | None:
        with session_scope() as session:
            model = session.get(AISettingsModel, entity_id)
            return _to_output(model) if model is not None else None

    def update(self, entity_id: int, entity: AISettingsIn) -> AISettingsOut:
        return self._save(entity_id, entity)

    def delete(self, entity_id: int) -> bool:
        with session_scope() as session:
            model = session.get(AISettingsModel, entity_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def list(self, options: EmptyListOptions | None = None) -> list[AISettingsOut]:
        del options
        settings = self.get(1)
        return [settings] if settings is not None else []

    @staticmethod
    def _save(entity_id: int, entity: AISettingsIn) -> AISettingsOut:
        with session_scope() as session:
            model = session.get(AISettingsModel, entity_id)
            if model is None:
                model = AISettingsModel(id=entity_id)
                session.add(model)
            if entity.api_key is not None and entity.api_key.strip():
                model.encrypted_api_key = encrypt_api_key(entity.api_key)
            model.provider = entity.provider
            model.model = entity.model
            model.base_url = entity.base_url
            model.temperature = entity.temperature
            model.enabled = entity.enabled
            model.updated_at = datetime.now(UTC)
            session.flush()
            return _to_output(model)


ai_settings_storage = AISettingsStorage()

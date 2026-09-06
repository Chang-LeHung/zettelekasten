import base64
import hashlib
import os
from datetime import UTC, datetime

from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import AIProviderListOptions
from ..schemas import AIProviderIn, AIProviderOut
from .database import session_scope
from .models import AIProviderModel, AISettingsModel
from .storage import Storage


class AIProviderConnection(BaseModel):
    """Decrypted provider configuration consumed only while constructing a model."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    base_url: str | None
    api_key: SecretStr | None
    temperature: float
    enabled: bool


def _fernet() -> Fernet:
    """Build the local encryption wrapper without persisting its derived key."""
    secret = os.getenv("ZETT_SECRET_KEY", "zett-local-secret")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt a provider API key before it enters a database model."""
    return _fernet().encrypt(api_key.encode()).decode()


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-naive timestamps to explicit UTC values."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_output(model: AIProviderModel) -> AIProviderOut:
    """Detach safe provider metadata from its SQLAlchemy session."""
    return AIProviderOut(
        id=model.id,
        name=model.name,
        provider=model.provider,
        model=model.model,
        base_url=model.base_url,
        temperature=model.temperature,
        enabled=model.enabled,
        api_key_configured=bool(model.encrypted_api_key),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _migrate_legacy_provider(session: Session) -> None:
    """Copy the former singleton settings row into the provider collection once."""
    if session.scalar(select(AIProviderModel.id).limit(1)) is not None:
        return
    legacy = session.get(AISettingsModel, 1)
    if legacy is None:
        return
    now = datetime.now(UTC)
    session.add(
        AIProviderModel(
            name=f"{legacy.provider} · {legacy.model}",
            provider=legacy.provider,
            model=legacy.model,
            base_url=legacy.base_url,
            encrypted_api_key=legacy.encrypted_api_key,
            temperature=legacy.temperature,
            enabled=legacy.enabled,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()


class AIProviderStorage(Storage[AIProviderIn, AIProviderOut, int, AIProviderListOptions]):
    """SQLAlchemy storage adapter for encrypted AI provider configurations."""

    def create(self, entity: AIProviderIn) -> AIProviderOut:
        now = datetime.now(UTC)
        with session_scope() as session:
            model = AIProviderModel(
                name=entity.name,
                provider=entity.provider,
                model=entity.model,
                base_url=entity.base_url,
                encrypted_api_key=encrypt_api_key(entity.api_key) if entity.api_key else None,
                temperature=entity.temperature,
                enabled=entity.enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return _to_output(model)

    def get(self, entity_id: int) -> AIProviderOut | None:
        with session_scope() as session:
            model = session.get(AIProviderModel, entity_id)
            return _to_output(model) if model is not None else None

    def update(self, entity_id: int, entity: AIProviderIn) -> AIProviderOut:
        with session_scope() as session:
            model = session.get(AIProviderModel, entity_id)
            if model is None:
                raise HTTPException(404, "AI provider not found")
            model.name = entity.name
            model.provider = entity.provider
            model.model = entity.model
            model.base_url = entity.base_url
            model.temperature = entity.temperature
            model.enabled = entity.enabled
            model.updated_at = datetime.now(UTC)
            if entity.api_key:
                model.encrypted_api_key = encrypt_api_key(entity.api_key)
            session.flush()
            return _to_output(model)

    def delete(self, entity_id: int) -> bool:
        with session_scope() as session:
            model = session.get(AIProviderModel, entity_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def list(self, options: AIProviderListOptions | None = None) -> list[AIProviderOut]:
        options = options or AIProviderListOptions()
        with session_scope() as session:
            _migrate_legacy_provider(session)
            statement = select(AIProviderModel)
            if options.query:
                pattern = f"%{options.query}%"
                statement = statement.where(
                    or_(AIProviderModel.name.ilike(pattern), AIProviderModel.model.ilike(pattern))
                )
            if options.provider:
                statement = statement.where(AIProviderModel.provider == options.provider)
            if options.enabled is not None:
                statement = statement.where(AIProviderModel.enabled.is_(options.enabled))
            models = session.scalars(
                statement.order_by(AIProviderModel.name, AIProviderModel.id).offset(options.offset).limit(options.limit)
            ).all()
            return [_to_output(model) for model in models]

    def resolve_connection(self, provider_id: int | None = None) -> AIProviderConnection | None:
        """Resolve and decrypt one enabled provider for immediate model construction."""
        with session_scope() as session:
            if provider_id is not None:
                model = session.get(AIProviderModel, provider_id)
            else:
                _migrate_legacy_provider(session)
                model = session.scalars(
                    select(AIProviderModel)
                    .where(AIProviderModel.enabled.is_(True))
                    .order_by(AIProviderModel.name, AIProviderModel.id)
                ).first()
            if model is None:
                return None
            encrypted_key = model.encrypted_api_key
            api_key = _fernet().decrypt(encrypted_key.encode()).decode() if encrypted_key else None
            return AIProviderConnection(
                provider=model.provider,
                model=model.model,
                base_url=model.base_url,
                api_key=SecretStr(api_key) if api_key else None,
                temperature=model.temperature,
                enabled=model.enabled,
            )


ai_provider_storage = AIProviderStorage()

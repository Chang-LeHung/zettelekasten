"""Encrypted local storage for model provider configurations."""

import json
import os
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, select
from zett_agent import new_uuid7

from ...config import settings
from ...models import ProviderListOptions
from ...schemas import ProviderConnection, ProviderOut, ProviderType, ProviderWrite
from ..database import session_scope
from ..models import ProviderModel
from ..storage import Storage


class ProviderTypeCode(IntEnum):
    """Integer representation of provider protocols in the DAO layer."""

    OPENAI = 1
    ANTHROPIC = 2
    DEEPSEEK = 3
    GOOGLE = 4
    OLLAMA = 5
    OPENAI_COMPATIBLE = 6


TYPE_TO_CODE = {
    ProviderType.OPENAI: ProviderTypeCode.OPENAI,
    ProviderType.ANTHROPIC: ProviderTypeCode.ANTHROPIC,
    ProviderType.DEEPSEEK: ProviderTypeCode.DEEPSEEK,
    ProviderType.GOOGLE: ProviderTypeCode.GOOGLE,
    ProviderType.OLLAMA: ProviderTypeCode.OLLAMA,
    ProviderType.OPENAI_COMPATIBLE: ProviderTypeCode.OPENAI_COMPATIBLE,
}
CODE_TO_TYPE = {int(code): provider for provider, code in TYPE_TO_CODE.items()}


def _as_utc(value: datetime) -> datetime:
    """Restore the UTC marker omitted by SQLite's timestamp representation."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _read_or_create_key(path: Path) -> bytes:
    """Return a private Fernet key, creating it atomically with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_bytes()
    else:
        try:
            key = Fernet.generate_key()
            os.write(descriptor, key)
        finally:
            os.close(descriptor)
    try:
        os.chmod(path, 0o600)
        Fernet(key)
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Invalid provider encryption key: {path}") from error
    return key


def _fernet() -> Fernet:
    return Fernet(_read_or_create_key(settings.provider_key_path))


def _encrypt_api_key(api_key: str | None) -> str | None:
    return _fernet().encrypt(api_key.encode()).decode() if api_key is not None else None


def _decrypt_api_key(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as error:
        raise RuntimeError("Stored provider API key cannot be decrypted with the local key") from error


def _provider_out(model: ProviderModel) -> ProviderOut:
    """Detach safe metadata without exposing ciphertext or plaintext credentials."""
    return ProviderOut(
        id=model.id,
        name=model.name,
        provider=CODE_TO_TYPE[model.provider],
        model=model.model,
        base_url=model.base_url,
        api_key_configured=model.encrypted_api_key is not None,
        enabled=model.enabled,
        metadata=json.loads(model.metadata_value),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class ProviderStorage(Storage[ProviderWrite, ProviderOut, str, ProviderListOptions]):
    """Store model configurations while keeping API keys encrypted at rest.

    ``get`` and ``list`` return safe models with only ``api_key_configured``.
    ``resolve_connection`` is the narrow credential boundary for a future model
    factory. Updating is a complete replacement; ``api_key=None`` clears the
    previously stored credential.
    """

    def create(self, entity: ProviderWrite) -> ProviderOut:
        now = datetime.now(UTC)
        with session_scope() as session:
            model = ProviderModel(
                id=new_uuid7(),
                name=entity.name,
                provider=int(TYPE_TO_CODE[entity.provider]),
                model=entity.model,
                base_url=entity.base_url,
                encrypted_api_key=_encrypt_api_key(entity.api_key),
                enabled=entity.enabled,
                metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return _provider_out(model)

    def get(self, entity_id: str) -> ProviderOut | None:
        with session_scope() as session:
            model = session.get(ProviderModel, entity_id)
            return _provider_out(model) if model is not None else None

    def update(self, entity_id: str, entity: ProviderWrite) -> ProviderOut:
        with session_scope() as session:
            model = session.get(ProviderModel, entity_id)
            if model is None:
                raise KeyError(f"Provider not found: {entity_id}")
            model.name = entity.name
            model.provider = int(TYPE_TO_CODE[entity.provider])
            model.model = entity.model
            model.base_url = entity.base_url
            model.encrypted_api_key = _encrypt_api_key(entity.api_key)
            model.enabled = entity.enabled
            model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
            model.updated_at = datetime.now(UTC)
            session.flush()
            return _provider_out(model)

    def delete(self, entity_id: str) -> bool:
        with session_scope() as session:
            model = session.get(ProviderModel, entity_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def list(self, options: ProviderListOptions | None = None) -> list[ProviderOut]:
        options = options or ProviderListOptions()
        with session_scope() as session:
            statement = select(ProviderModel)
            if options.query:
                pattern = f"%{options.query}%"
                statement = statement.where(or_(ProviderModel.name.ilike(pattern), ProviderModel.model.ilike(pattern)))
            if options.providers:
                codes = [int(TYPE_TO_CODE[ProviderType(provider)]) for provider in options.providers]
                statement = statement.where(ProviderModel.provider.in_(codes))
            if options.enabled is not None:
                statement = statement.where(ProviderModel.enabled.is_(options.enabled))
            statement = (
                statement.order_by(ProviderModel.name, ProviderModel.id).limit(options.limit).offset(options.offset)
            )
            return [_provider_out(model) for model in session.scalars(statement)]

    def resolve_connection(self, entity_id: str | None = None) -> ProviderConnection | None:
        """Decrypt one enabled configuration for immediate model construction."""
        with session_scope() as session:
            if entity_id is None:
                model = session.scalars(
                    select(ProviderModel)
                    .where(ProviderModel.enabled.is_(True))
                    .order_by(ProviderModel.name, ProviderModel.id)
                    .limit(1)
                ).first()
            else:
                model = session.get(ProviderModel, entity_id)
            if model is None or not model.enabled:
                return None
            api_key = _decrypt_api_key(model.encrypted_api_key)
            return ProviderConnection(
                id=model.id,
                provider=CODE_TO_TYPE[model.provider],
                model=model.model,
                base_url=model.base_url,
                api_key=api_key,
                metadata=json.loads(model.metadata_value),
            )


provider_storage = ProviderStorage()

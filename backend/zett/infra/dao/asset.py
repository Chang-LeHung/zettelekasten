import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from zett_agent import new_uuid7

from ...config import settings
from ...models import SessionAssetListOptions
from ...schemas import SessionAssetCreate, SessionAssetOut, SessionAssetType
from ..database import session_scope
from ..models import SessionAssetModel
from ..storage import Storage


class AssetTypeCode(IntEnum):
    """Numeric persistence representation for finite session asset types."""

    TEXT = 1
    IMAGE = 2
    LINK = 3
    FILE = 4


ASSET_TO_CODE = {
    SessionAssetType.TEXT: AssetTypeCode.TEXT,
    SessionAssetType.IMAGE: AssetTypeCode.IMAGE,
    SessionAssetType.LINK: AssetTypeCode.LINK,
    SessionAssetType.FILE: AssetTypeCode.FILE,
}
CODE_TO_ASSET = {int(code): asset_type for asset_type, code in ASSET_TO_CODE.items()}
FILE_ASSET_TYPES = (SessionAssetType.IMAGE, SessionAssetType.FILE)


def _asset_out(model: SessionAssetModel) -> SessionAssetOut:
    """Convert one ORM row into the typed public asset representation."""
    asset_type = CODE_TO_ASSET[model.asset_type]
    return SessionAssetOut(
        id=model.id,
        session_id=model.session_id,
        asset_type=asset_type,
        name=model.name,
        mime_type=model.mime_type,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        text_content=model.text_content,
        source_url=model.source_url,
        content_url=(
            f"/api/agent/{model.session_id}/assets/{model.id}/content" if asset_type != SessionAssetType.LINK else None
        ),
        metadata=json.loads(model.metadata_value),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _safe_suffix(name: str) -> str:
    """Keep a short extension for content disposition without trusting user paths."""
    suffix = Path(name).suffix.lower()[:16]
    return suffix if re.fullmatch(r"\.[a-z0-9]+", suffix) else ""


def _validate_payload(entity: SessionAssetCreate) -> None:
    """Validate content consistently before any database or filesystem mutation."""
    match entity.asset_type:
        case SessionAssetType.IMAGE | SessionAssetType.FILE:
            if entity.content is None:
                raise ValueError("Binary asset content is required")
        case SessionAssetType.TEXT:
            if entity.text_content is None:
                raise ValueError("Text asset content is required")
        case SessionAssetType.LINK:
            if not entity.source_url:
                raise ValueError("Link asset URL is required")
    payload = (
        entity.content if entity.content is not None else (entity.text_content or entity.source_url or "").encode()
    )
    if len(payload) > settings.max_asset_size_bytes:
        raise ValueError("Asset exceeds the configured size limit")


class SessionAssetStorage(Storage[SessionAssetCreate, SessionAssetOut, str, SessionAssetListOptions]):
    """Persist session asset metadata in SQLite and binary payloads on local disk."""

    def create(self, entity: SessionAssetCreate) -> SessionAssetOut:
        _validate_payload(entity)
        asset_id = new_uuid7()
        now = datetime.now(UTC)
        storage_name: str | None = None
        written_path: Path | None = None
        from ..agent_runtime import get_agent_runtime_storage

        if get_agent_runtime_storage().get_session(entity.session_id) is None:
            raise KeyError(f"Agent session not found: {entity.session_id}")
        if entity.asset_type in FILE_ASSET_TYPES:
            if entity.content is None:
                raise ValueError("Binary asset content is required")
            storage_name = f"{asset_id}{_safe_suffix(entity.name)}"
            written_path = self._session_directory(entity.session_id) / storage_name
            written_path.write_bytes(entity.content)
        elif entity.asset_type == SessionAssetType.TEXT and entity.text_content is None:
            raise ValueError("Text asset content is required")
        elif entity.asset_type == SessionAssetType.LINK and entity.source_url is None:
            raise ValueError("Link asset URL is required")

        payload = entity.content or (entity.text_content or entity.source_url or "").encode()
        try:
            with session_scope() as session:
                model = SessionAssetModel(
                    id=asset_id,
                    session_id=entity.session_id,
                    asset_type=int(ASSET_TO_CODE[entity.asset_type]),
                    name=entity.name,
                    mime_type=entity.mime_type,
                    size_bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    storage_name=storage_name,
                    text_content=entity.text_content,
                    source_url=entity.source_url,
                    metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                session.flush()
                result = _asset_out(model)
            return result
        except Exception:
            if written_path is not None:
                written_path.unlink(missing_ok=True)
                self._remove_empty_directory(entity.session_id)
            raise

    def get(self, entity_id: str) -> SessionAssetOut | None:
        with session_scope() as session:
            model = session.get(SessionAssetModel, entity_id)
            return _asset_out(model) if model else None

    def update(self, entity_id: str, entity: SessionAssetCreate) -> SessionAssetOut:
        _validate_payload(entity)
        replacement_path: Path | None = None
        old_path: Path | None = None
        try:
            with session_scope() as session:
                model = session.get(SessionAssetModel, entity_id)
                if model is None or model.session_id != entity.session_id:
                    raise KeyError(f"Session asset not found: {entity_id}")
                if model.storage_name:
                    old_path = self._session_directory(model.session_id) / model.storage_name
                payload = entity.content or (entity.text_content or entity.source_url or "").encode()
                storage_name: str | None = None
                if entity.asset_type in FILE_ASSET_TYPES:
                    if entity.content is None:
                        raise ValueError("Binary asset content is required")
                    revision = new_uuid7()
                    storage_name = f"{entity_id}-{revision}{_safe_suffix(entity.name)}"
                    replacement_path = self._session_directory(entity.session_id) / storage_name
                    replacement_path.write_bytes(entity.content)
                model.asset_type = int(ASSET_TO_CODE[entity.asset_type])
                model.name = entity.name
                model.mime_type = entity.mime_type
                model.size_bytes = len(payload)
                model.sha256 = hashlib.sha256(payload).hexdigest()
                model.storage_name = storage_name
                model.text_content = entity.text_content
                model.source_url = entity.source_url
                model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
                model.updated_at = datetime.now(UTC)
                session.flush()
                result = _asset_out(model)
        except Exception:
            if replacement_path is not None:
                replacement_path.unlink(missing_ok=True)
            raise
        if old_path is not None and old_path != replacement_path:
            old_path.unlink(missing_ok=True)
        return result

    def rename(self, session_id: str, entity_id: str, name: str) -> SessionAssetOut:
        """Change display metadata only; never rewrite bytes or their UUID path."""
        with session_scope() as session:
            model = session.get(SessionAssetModel, entity_id)
            if model is None or model.session_id != session_id:
                raise KeyError(f"Session asset not found: {entity_id}")
            model.name = name
            model.updated_at = datetime.now(UTC)
            session.flush()
            return _asset_out(model)

    def delete(self, entity_id: str) -> bool:
        stored_path: Path | None = None
        session_id: str | None = None
        with session_scope() as session:
            model = session.get(SessionAssetModel, entity_id)
            if model is None:
                return False
            session_id = model.session_id
            if model.storage_name:
                stored_path = self._session_directory(model.session_id) / model.storage_name
            session.delete(model)
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        if session_id is not None:
            self._remove_empty_directory(session_id)
        return True

    def list(self, options: SessionAssetListOptions | None = None) -> list[SessionAssetOut]:
        options = options or SessionAssetListOptions()
        with session_scope() as session:
            statement = select(SessionAssetModel)
            if options.session_id:
                statement = statement.where(SessionAssetModel.session_id == options.session_id)
            if options.query:
                statement = statement.where(SessionAssetModel.name.ilike(f"%{options.query}%"))
            if options.asset_types:
                codes = [int(ASSET_TO_CODE[SessionAssetType(value)]) for value in options.asset_types]
                statement = statement.where(SessionAssetModel.asset_type.in_(codes))
            statement = (
                statement.order_by(SessionAssetModel.created_at, SessionAssetModel.id)
                .limit(options.limit)
                .offset(options.offset)
            )
            return [_asset_out(model) for model in session.scalars(statement)]

    def get_for_session(self, session_id: str, asset_id: str) -> SessionAssetOut | None:
        """Read an asset only when it belongs to the requested session."""
        asset = self.get(asset_id)
        return asset if asset and asset.session_id == session_id else None

    def content_path(self, session_id: str, asset_id: str) -> Path | None:
        """Resolve a stored binary path after verifying session ownership."""
        with session_scope() as session:
            model = session.get(SessionAssetModel, asset_id)
            if model is None or model.session_id != session_id or not model.storage_name:
                return None
            path = self._session_directory(session_id) / model.storage_name
            return path if path.is_file() else None

    def delete_session(self, session_id: str) -> None:
        """Explicitly remove all metadata and files owned by one session."""
        with session_scope() as session:
            session.execute(sql_delete(SessionAssetModel).where(SessionAssetModel.session_id == session_id))
        directory = self._session_path(session_id)
        if directory.is_dir():
            shutil.rmtree(directory)

    @staticmethod
    def _session_directory(session_id: str) -> Path:
        directory = SessionAssetStorage._session_path(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _session_path(session_id: str) -> Path:
        """Map a canonical UUID to a direct child of the configured asset root."""
        try:
            normalized_id = str(UUID(session_id))
        except ValueError as error:
            raise ValueError("Session ID must be a canonical UUID") from error
        if normalized_id != session_id:
            raise ValueError("Session ID must be a canonical UUID")
        return settings.asset_directory / normalized_id

    @staticmethod
    def _remove_empty_directory(session_id: str) -> None:
        directory = SessionAssetStorage._session_path(session_id)
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


session_asset_storage = SessionAssetStorage()

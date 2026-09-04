import json
from datetime import UTC, datetime
from enum import IntEnum
from typing import cast
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from ..models import ArtifactListOptions
from ..schemas import AgentArtifact, AgentArtifactWrite, ArtifactContent, ArtifactStatus, ArtifactType
from .database import session_scope
from .models import AgentSessionModel, SessionArtifactModel
from .storage import Storage


class ArtifactTypeCode(IntEnum):
    CARD = 1
    ARTICLE = 2
    IMAGE = 3


class ArtifactStatusCode(IntEnum):
    DRAFT = 1
    SAVED = 2


TYPE_TO_CODE = {
    ArtifactType.CARD: ArtifactTypeCode.CARD,
    ArtifactType.ARTICLE: ArtifactTypeCode.ARTICLE,
    ArtifactType.IMAGE: ArtifactTypeCode.IMAGE,
}
CODE_TO_TYPE = {int(code): value for value, code in TYPE_TO_CODE.items()}
STATUS_TO_CODE = {
    ArtifactStatus.DRAFT: ArtifactStatusCode.DRAFT,
    ArtifactStatus.SAVED: ArtifactStatusCode.SAVED,
}
CODE_TO_STATUS = {int(code): value for value, code in STATUS_TO_CODE.items()}
CONTENT_ADAPTER = TypeAdapter(ArtifactContent)


def _json_load[JSONValueT](value: str | None, fallback: JSONValueT) -> JSONValueT:
    """Decode persisted JSON while preserving the caller's fallback type."""
    try:
        return cast(JSONValueT, json.loads(value)) if value else fallback
    except json.JSONDecodeError:
        return fallback


def _artifact_out(model: SessionArtifactModel) -> AgentArtifact:
    """Hydrate a typed artifact from its ORM record and discriminated JSON content."""
    return AgentArtifact(
        id=model.id,
        session_id=model.session_id,
        artifact_type=CODE_TO_TYPE[model.artifact_type],
        status=CODE_TO_STATUS[model.status],
        content=CONTENT_ADAPTER.validate_python(_json_load(model.content_json, {})),
        raw_content=model.raw_content,
        linked_resource_id=model.linked_resource_id,
        version=model.version,
        metadata=_json_load(model.metadata_json, {}),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class ArtifactStorage(Storage[AgentArtifactWrite, AgentArtifact, str, ArtifactListOptions]):
    """SQLAlchemy storage for polymorphic, session-owned artifacts."""

    def create(self, entity: AgentArtifactWrite) -> AgentArtifact:
        now = datetime.now(UTC)
        with session_scope() as session:
            if session.get(AgentSessionModel, entity.session_id) is None:
                raise KeyError(f"Agent session not found: {entity.session_id}")
            model = SessionArtifactModel(
                id=str(uuid4()),
                session_id=entity.session_id,
                artifact_type=int(TYPE_TO_CODE[entity.content.artifact_type]),
                status=int(STATUS_TO_CODE[entity.status]),
                title=entity.content.title,
                content_json=entity.content.model_dump_json(),
                raw_content=entity.raw_content,
                linked_resource_id=entity.linked_resource_id,
                version=1,
                metadata_json=json.dumps(entity.metadata, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return _artifact_out(model)

    def get(self, entity_id: str) -> AgentArtifact | None:
        with session_scope() as session:
            model = session.get(SessionArtifactModel, entity_id)
            return _artifact_out(model) if model else None

    def update(self, entity_id: str, entity: AgentArtifactWrite) -> AgentArtifact:
        with session_scope() as session:
            model = session.get(SessionArtifactModel, entity_id)
            if model is None or model.session_id != entity.session_id:
                raise KeyError(f"Artifact not found: {entity_id}")
            model.artifact_type = int(TYPE_TO_CODE[entity.content.artifact_type])
            model.status = int(STATUS_TO_CODE[entity.status])
            model.title = entity.content.title
            model.content_json = entity.content.model_dump_json()
            model.raw_content = entity.raw_content
            model.linked_resource_id = entity.linked_resource_id
            model.metadata_json = json.dumps(entity.metadata, ensure_ascii=False)
            model.version += 1
            model.updated_at = datetime.now(UTC)
            session.flush()
            return _artifact_out(model)

    def delete(self, entity_id: str) -> bool:
        with session_scope() as session:
            model = session.get(SessionArtifactModel, entity_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def list(self, options: ArtifactListOptions | None = None) -> list[AgentArtifact]:
        options = options or ArtifactListOptions()
        with session_scope() as session:
            statement = select(SessionArtifactModel)
            if options.session_id:
                statement = statement.where(SessionArtifactModel.session_id == options.session_id)
            if options.artifact_types:
                codes = [int(TYPE_TO_CODE[ArtifactType(value)]) for value in options.artifact_types]
                statement = statement.where(SessionArtifactModel.artifact_type.in_(codes))
            if options.statuses:
                codes = [int(STATUS_TO_CODE[ArtifactStatus(value)]) for value in options.statuses]
                statement = statement.where(SessionArtifactModel.status.in_(codes))
            if options.query:
                statement = statement.where(SessionArtifactModel.title.ilike(f"%{options.query}%"))
            statement = statement.order_by(SessionArtifactModel.created_at).limit(options.limit).offset(options.offset)
            return [_artifact_out(model) for model in session.scalars(statement)]

    def delete_session(self, session_id: str) -> int:
        """Explicitly remove every artifact owned by a deleted session."""
        with session_scope() as session:
            result = session.execute(
                sql_delete(SessionArtifactModel).where(SessionArtifactModel.session_id == session_id)
            )
            return result.rowcount


artifact_storage = ArtifactStorage()

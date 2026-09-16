import asyncio
import json
from datetime import UTC, datetime
from enum import IntEnum
from typing import cast

from pydantic import TypeAdapter
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from zett_agent import new_uuid7

from ...models import ArtifactListOptions
from ...schemas import (
    AgentArtifact,
    AgentArtifactWrite,
    ArtifactContent,
    ArtifactStatus,
    ArtifactTagOut,
    ArtifactType,
    LatexPdfArtifactContent,
    LatexPdfArtifactCreate,
)
from ..database import session_scope
from ..latex_projects import create_latex_project, validate_latex_project_path
from ..models import ArtifactTagModel, SessionArtifactModel
from ..storage import Storage


class ArtifactTypeCode(IntEnum):
    CARD = 1
    ARTICLE = 2
    IMAGE = 3
    SLIDES = 4
    LATEX_PDF = 5


class ArtifactStatusCode(IntEnum):
    DRAFT = 1
    SAVED = 2


TYPE_TO_CODE = {
    ArtifactType.CARD: ArtifactTypeCode.CARD,
    ArtifactType.ARTICLE: ArtifactTypeCode.ARTICLE,
    ArtifactType.IMAGE: ArtifactTypeCode.IMAGE,
    ArtifactType.SLIDES: ArtifactTypeCode.SLIDES,
    ArtifactType.LATEX_PDF: ArtifactTypeCode.LATEX_PDF,
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


def _artifact_out(model: SessionArtifactModel, *, tags: list[ArtifactTagOut] | None = None) -> AgentArtifact:
    """Hydrate a typed artifact from its ORM record and discriminated JSON content."""
    return AgentArtifact(
        id=model.id,
        session_id=model.session_id,
        artifact_type=CODE_TO_TYPE[model.artifact_type],
        status=CODE_TO_STATUS[model.status],
        content=CONTENT_ADAPTER.validate_python(_json_load(model.content_json, {})),
        raw_content=model.raw_content,
        version=model.version,
        metadata=_json_load(model.metadata_value, {}),
        created_at=model.created_at,
        updated_at=model.updated_at,
        tags=tags or [],
    )


class ArtifactStorage(Storage[AgentArtifactWrite, AgentArtifact, str, ArtifactListOptions]):
    """SQLAlchemy storage for polymorphic, session-owned artifacts."""

    async def create(self, entity: AgentArtifactWrite) -> AgentArtifact:
        """Persist one artifact after confirming its Agent session exists.

        The session database is asynchronous, so this boundary awaits it and
        then runs the application-database write in a worker thread.
        """
        from ..agent_runtime import get_agent_runtime_storage

        if await get_agent_runtime_storage().get_session(entity.session_id) is None:
            raise KeyError(f"Agent session not found: {entity.session_id}")
        return await asyncio.to_thread(self._create, entity)

    def _create(self, entity: AgentArtifactWrite) -> AgentArtifact:
        now = datetime.now(UTC)
        content = entity.content
        if isinstance(content, LatexPdfArtifactCreate):
            content = create_latex_project(entity.session_id, content)
        with session_scope() as session:
            model = SessionArtifactModel(
                id=new_uuid7(),
                session_id=entity.session_id,
                artifact_type=int(TYPE_TO_CODE[entity.content.artifact_type]),
                status=int(STATUS_TO_CODE[entity.status]),
                title=entity.content.title,
                content_json=content.model_dump_json(),
                raw_content=entity.raw_content,
                version=1,
                metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return _artifact_out(model)

    def get(self, entity_id: str) -> AgentArtifact | None:
        with session_scope() as session:
            model = session.get(SessionArtifactModel, entity_id)
            artifact = _artifact_out(model) if model else None
        if artifact is None:
            return None
        from .tag import tag_storage

        tags = tag_storage.tags_for_artifacts((entity_id,)).get(entity_id, [])
        return artifact.model_copy(update={"tags": tags})

    def get_for_session(self, session_id: str, artifact_id: str) -> AgentArtifact | None:
        """Read an artifact only when it belongs to the requested session."""
        artifact = self.get(artifact_id)
        return artifact if artifact is not None and artifact.session_id == session_id else None

    def update(self, entity_id: str, entity: AgentArtifactWrite) -> AgentArtifact:
        if isinstance(entity.content, LatexPdfArtifactCreate) and not isinstance(
            entity.content, LatexPdfArtifactContent
        ):
            raise ValueError("Updates must include the server-assigned project_path")
        if isinstance(entity.content, LatexPdfArtifactContent):
            # A draft or saved reference can precede compilation; only validate its location.
            validate_latex_project_path(entity.session_id, entity.content)
        with session_scope() as session:
            model = session.get(SessionArtifactModel, entity_id)
            if model is None or model.session_id != entity.session_id:
                raise KeyError(f"Artifact not found: {entity_id}")
            model.artifact_type = int(TYPE_TO_CODE[entity.content.artifact_type])
            model.status = int(STATUS_TO_CODE[entity.status])
            model.title = entity.content.title
            model.content_json = entity.content.model_dump_json()
            model.raw_content = entity.raw_content
            model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
            model.version += 1
            model.updated_at = datetime.now(UTC)
            session.flush()
            return _artifact_out(model)

    def delete(self, entity_id: str) -> bool:
        with session_scope() as session:
            model = session.get(SessionArtifactModel, entity_id)
            if model is None:
                return False
            session.execute(sql_delete(ArtifactTagModel).where(ArtifactTagModel.artifact_id == entity_id))
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
            if options.tag_ids:
                statement = statement.where(
                    SessionArtifactModel.id.in_(
                        select(ArtifactTagModel.artifact_id).where(ArtifactTagModel.tag_id.in_(options.tag_ids))
                    )
                )
            if options.query:
                statement = statement.where(SessionArtifactModel.title.ilike(f"%{options.query}%"))
            statement = statement.order_by(SessionArtifactModel.created_at).limit(options.limit).offset(options.offset)
            artifacts = [_artifact_out(model) for model in session.scalars(statement)]
        from .tag import tag_storage

        tags = tag_storage.tags_for_artifacts(tuple(artifact.id for artifact in artifacts))
        return [artifact.model_copy(update={"tags": tags.get(artifact.id, [])}) for artifact in artifacts]

    def delete_session(self, session_id: str) -> int:
        """Explicitly remove every artifact owned by a deleted session."""
        with session_scope() as session:
            artifact_ids = tuple(
                session.scalars(select(SessionArtifactModel.id).where(SessionArtifactModel.session_id == session_id))
            )
            if artifact_ids:
                session.execute(sql_delete(ArtifactTagModel).where(ArtifactTagModel.artifact_id.in_(artifact_ids)))
            result = session.execute(
                sql_delete(SessionArtifactModel).where(SessionArtifactModel.session_id == session_id)
            )
            return result.rowcount


artifact_storage = ArtifactStorage()

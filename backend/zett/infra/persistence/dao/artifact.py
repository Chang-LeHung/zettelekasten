from __future__ import annotations

import json
from datetime import datetime
from typing import TypeVar, cast

from pydantic import TypeAdapter
from sqlalchemy import Float, Select, String, Subquery, func, or_, select, text
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update
from zett_agent.ids import new_uuid7

from ...._compat import UTC
from ....application.files.object_store import InvalidObjectKey, ObjectKey, session_directory_key
from ....schemas import (
    AgentArtifactEntity,
    AgentArtifactWrite,
    ArtifactContent,
    ArtifactListOptions,
    ArtifactStatus,
    ArtifactType,
    ImageArtifactContent,
    LatexPdfArtifactContent,
    LatexPdfArtifactCreate,
    TagRefEntity,
    TagTargetType,
)
from ...artifacts.latex_projects import create_latex_project, validate_latex_project_path
from ...artifacts.search import (
    build_fts_query,
    delete_artifact_search,
    delete_artifacts_search,
    upsert_artifact_search,
)
from ...files.object_store import get_object_store
from ..database import session_scope
from ..storage import AsyncStorage
from ..tables import (
    CODE_TO_STATUS,
    CODE_TO_TYPE,
    STATUS_TO_CODE,
    TARGET_TO_CODE,
    TYPE_TO_CODE,
    SessionArtifactRow,
    TagLinkRow,
)

CONTENT_ADAPTER = TypeAdapter(ArtifactContent)

JSONValueT = TypeVar("JSONValueT")


class ArtifactVersionConflictError(ValueError):
    """The row was changed since an external editor read it."""


def _json_load(value: str | None, fallback: JSONValueT) -> JSONValueT:
    """Decode persisted JSON while preserving the caller's fallback type."""
    try:
        return cast(JSONValueT, json.loads(value)) if value else fallback
    except json.JSONDecodeError:
        return fallback


def _artifact_out(model: SessionArtifactRow, *, tags: list[TagRefEntity] | None = None) -> AgentArtifactEntity:
    """Hydrate a typed artifact from its ORM record and discriminated JSON content."""
    content = _content(model.content_json)
    draft_content = _content(model.draft_content_json)
    editable = content or draft_content
    content_url: str | None = None
    if isinstance(editable, LatexPdfArtifactContent):
        content_url = get_object_store().url(ObjectKey(f"{editable.project_path}/{editable.pdf_name}"))
    elif isinstance(editable, ImageArtifactContent) and editable.asset_path:
        content_url = get_object_store().url(editable.asset_path)
    return AgentArtifactEntity(
        id=model.id,
        session_id=model.session_id,
        artifact_type=CODE_TO_TYPE[model.artifact_type],
        status=CODE_TO_STATUS[model.status],
        content=content,
        draft_content=draft_content,
        raw_content=model.raw_content,
        version=model.version,
        metadata=_json_load(model.metadata_value, {}),
        created_at=model.created_at,
        updated_at=model.updated_at,
        tags=tags or [],
        content_url=content_url,
    )


def _content(value: str | None) -> ArtifactContent | None:
    """Decode one stored content column; an empty column carries no content."""
    decoded = _json_load(value, None)
    return None if decoded is None else CONTENT_ADAPTER.validate_python(decoded)


def _store_content(content: ArtifactContent | None) -> str:
    """Encode one content column, using an empty string for "not written yet"."""
    return "" if content is None else content.model_dump_json()


def _created_content(
    session_id: str,
    content: ArtifactContent | LatexPdfArtifactCreate | None,
) -> ArtifactContent | None:
    """Resolve one create payload, allocating a LaTeX project when requested."""
    if isinstance(content, LatexPdfArtifactCreate):
        return create_latex_project(session_id, content)
    _validate_image_path(session_id, content)
    return content


def _updated_content(
    session_id: str,
    content: ArtifactContent | LatexPdfArtifactCreate | None,
) -> ArtifactContent | None:
    """Resolve one update payload, requiring the server-assigned LaTeX project."""
    if isinstance(content, LatexPdfArtifactCreate) and not isinstance(content, LatexPdfArtifactContent):
        raise ValueError("Updates must include the server-assigned project_path")
    if isinstance(content, LatexPdfArtifactContent):
        # A draft or saved reference can precede compilation; only validate its location.
        validate_latex_project_path(session_id, content)
    _validate_image_path(session_id, content)
    return content


def _validate_image_path(session_id: str, content: ArtifactContent | None) -> None:
    """Require an image artifact's local file to exist and belong to this session.

    An image artifact points either outside the application (``source_url``) or
    at one file this conversation uploaded (``asset_path``). A path nobody owns,
    or one that names nothing on disk, would render as a broken image forever,
    so it is refused before it is stored instead of after the user opens it.
    """
    if not isinstance(content, ImageArtifactContent) or content.asset_path is None:
        return
    try:
        key = ObjectKey(content.asset_path)
    except InvalidObjectKey as error:
        raise ValueError(f"Image asset_path is not a relative object key: {content.asset_path!r}") from error
    directory = session_directory_key(session_id).value
    if not key.value.startswith(f"{directory}/"):
        raise ValueError("Image asset_path must be a file this conversation uploaded")
    if not get_object_store().resolve(key).is_file():
        raise ValueError(f"Image asset_path does not exist: {key.value}")


def _filtered_artifact_statement(
    options: ArtifactListOptions,
) -> tuple[Select[tuple[SessionArtifactRow]], Subquery | None]:
    """Build the artifact query with every list filter applied.

    ``list`` and ``count`` share this so a library total can never describe a
    different set than the pages it numbers. The returned rank column is the
    FTS relevance the ranked search orders by, or ``None`` when the query used
    the substring fallback.
    """
    statement = select(SessionArtifactRow)
    if options.published_only:
        statement = statement.where(
            SessionArtifactRow.status == int(STATUS_TO_CODE[ArtifactStatus.SAVED]),
            SessionArtifactRow.content_json != "",
        )
    if options.session_id:
        statement = statement.where(SessionArtifactRow.session_id == options.session_id)
    if options.artifact_types:
        codes = [int(TYPE_TO_CODE[ArtifactType(value)]) for value in options.artifact_types]
        statement = statement.where(SessionArtifactRow.artifact_type.in_(codes))
    if options.statuses:
        codes = [int(STATUS_TO_CODE[ArtifactStatus(value)]) for value in options.statuses]
        statement = statement.where(SessionArtifactRow.status.in_(codes))
    if options.tag_ids:
        statement = statement.where(
            SessionArtifactRow.id.in_(
                select(TagLinkRow.target_id).where(
                    TagLinkRow.target_type == int(TARGET_TO_CODE[TagTargetType.ARTIFACT]),
                    TagLinkRow.tag_id.in_(options.tag_ids),
                )
            )
        )
    rank = None
    if options.query:
        # The normal FTS document also indexes draft_content and raw_content.
        # An external knowledge search must not reveal their matches.
        fts_query = None if options.published_only else build_fts_query(options.query)
        if fts_query is None:
            pattern = f"%{options.query}%"
            columns = (
                (SessionArtifactRow.content_json,)
                if options.published_only
                else (
                    SessionArtifactRow.title,
                    SessionArtifactRow.content_json,
                    SessionArtifactRow.draft_content_json,
                    SessionArtifactRow.raw_content,
                )
            )
            statement = statement.where(or_(*(column.ilike(pattern) for column in columns)))
        else:
            rank = (
                text(
                    "SELECT artifact_id, bm25(artifact_search, 0.0, 8.0, 1.0) AS rank "
                    "FROM artifact_search "
                    "WHERE artifact_search MATCH :search_query"
                )
                .columns(artifact_id=String, rank=Float)
                .bindparams(search_query=fts_query)
                .subquery("artifact_search_rank")
            )
            statement = statement.join(rank, rank.c.artifact_id == SessionArtifactRow.id)
    return statement, rank


class ArtifactStorage(AsyncStorage[AgentArtifactWrite, AgentArtifactEntity, str, ArtifactListOptions]):
    """SQLAlchemy storage for polymorphic, session-owned artifacts."""

    async def create(self, entity: AgentArtifactWrite) -> AgentArtifactEntity:
        """Persist one artifact after confirming its Agent session exists."""
        from ...agent.runtime import get_agent_runtime_storage

        if await get_agent_runtime_storage().get_session(entity.session_id) is None:
            raise KeyError(f"Agent session not found: {entity.session_id}")
        now = datetime.now(UTC)
        content = _created_content(entity.session_id, entity.content)
        draft_content = _created_content(entity.session_id, entity.draft_content)
        described = content or draft_content
        async with session_scope() as session:
            model = SessionArtifactRow(
                id=new_uuid7(),
                session_id=entity.session_id,
                artifact_type=int(TYPE_TO_CODE[described.artifact_type]),
                status=int(STATUS_TO_CODE[entity.status]),
                title=described.title,
                content_json=_store_content(content),
                draft_content_json=_store_content(draft_content),
                raw_content=entity.raw_content,
                version=1,
                metadata_value=json.dumps(entity.metadata, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            await session.flush()
            await upsert_artifact_search(
                session,
                artifact_id=model.id,
                content=described,
                raw_content=entity.raw_content,
            )
            return _artifact_out(model)

    async def get(self, entity_id: str) -> AgentArtifactEntity | None:
        async with session_scope() as session:
            model = await session.get(SessionArtifactRow, entity_id)
            artifact = _artifact_out(model) if model else None
        if artifact is None:
            return None
        from .tag import tag_storage

        tags = (await tag_storage.tags_for(TagTargetType.ARTIFACT, (entity_id,))).get(entity_id, [])
        return artifact.model_copy(update={"tags": tags})

    async def get_for_session(self, session_id: str, artifact_id: str) -> AgentArtifactEntity | None:
        """Read an artifact only when it belongs to the requested session."""
        artifact = await self.get(artifact_id)
        return artifact if artifact is not None and artifact.session_id == session_id else None

    async def update(
        self,
        entity_id: str,
        entity: AgentArtifactWrite,
        *,
        expected_version: int | None = None,
        require_clean_draft: bool = False,
    ) -> AgentArtifactEntity:
        """Replace content, optionally refusing a stale version."""
        content = _updated_content(entity.session_id, entity.content)
        draft_content = _updated_content(entity.session_id, entity.draft_content)
        described = content or draft_content
        async with session_scope() as session:
            model = await session.get(SessionArtifactRow, entity_id)
            if model is None or model.session_id != entity.session_id:
                raise KeyError(f"Artifact not found: {entity_id}")
            if require_clean_draft and model.draft_content_json not in (None, "", model.content_json):
                raise ArtifactVersionConflictError("Artifact has an unpublished draft; review it before editing")
            if expected_version is not None:
                claimed = await session.execute(
                    sql_update(SessionArtifactRow)
                    .where(
                        SessionArtifactRow.id == entity_id,
                        SessionArtifactRow.session_id == entity.session_id,
                        SessionArtifactRow.version == expected_version,
                    )
                    .values(version=SessionArtifactRow.version + 1)
                    .execution_options(synchronize_session=False)
                )
                if claimed.rowcount != 1:
                    raise ArtifactVersionConflictError("Artifact changed; reload it before saving")
                await session.refresh(model)
            model.artifact_type = int(TYPE_TO_CODE[described.artifact_type])
            model.status = int(STATUS_TO_CODE[entity.status])
            model.title = described.title
            model.content_json = _store_content(content)
            model.draft_content_json = _store_content(draft_content)
            model.raw_content = entity.raw_content
            model.metadata_value = json.dumps(entity.metadata, ensure_ascii=False)
            if expected_version is None:
                model.version += 1
            model.updated_at = datetime.now(UTC)
            await session.flush()
            await upsert_artifact_search(
                session,
                artifact_id=model.id,
                content=described,
                raw_content=entity.raw_content,
            )
            return _artifact_out(model)

    async def delete(self, entity_id: str) -> bool:
        async with session_scope() as session:
            model = await session.get(SessionArtifactRow, entity_id)
            if model is None:
                return False
            await session.execute(
                sql_delete(TagLinkRow).where(
                    TagLinkRow.target_type == int(TARGET_TO_CODE[TagTargetType.ARTIFACT]),
                    TagLinkRow.target_id == entity_id,
                )
            )
            await delete_artifact_search(session, entity_id)
            await session.delete(model)
            return True

    async def list(self, options: ArtifactListOptions | None = None) -> list[AgentArtifactEntity]:
        options = options or ArtifactListOptions()
        async with session_scope() as session:
            statement, rank = _filtered_artifact_statement(options)
            order = (
                (rank.c.rank, SessionArtifactRow.updated_at.desc(), SessionArtifactRow.id.desc())
                if rank is not None
                else (SessionArtifactRow.updated_at.desc(), SessionArtifactRow.id.desc())
            )
            statement = statement.order_by(*order).limit(options.limit).offset(options.offset)
            artifacts = [_artifact_out(model) for model in await session.scalars(statement)]
        from .tag import tag_storage

        tags = await tag_storage.tags_for(TagTargetType.ARTIFACT, tuple(artifact.id for artifact in artifacts))
        return [artifact.model_copy(update={"tags": tags.get(artifact.id, [])}) for artifact in artifacts]

    async def count(self, options: ArtifactListOptions | None = None) -> int:
        """How many artifacts the same filters match; paging never changes it."""
        options = options or ArtifactListOptions()
        async with session_scope() as session:
            statement, _rank = _filtered_artifact_statement(options)
            total = await session.scalar(select(func.count()).select_from(statement.subquery()))
        return int(total or 0)

    async def delete_session(self, session_id: str) -> int:
        """Explicitly remove every artifact owned by a deleted session."""
        async with session_scope() as session:
            artifact_ids = tuple(
                await session.scalars(select(SessionArtifactRow.id).where(SessionArtifactRow.session_id == session_id))
            )
            if artifact_ids:
                await session.execute(
                    sql_delete(TagLinkRow).where(
                        TagLinkRow.target_type == int(TARGET_TO_CODE[TagTargetType.ARTIFACT]),
                        TagLinkRow.target_id.in_(artifact_ids),
                    )
                )
                await delete_artifacts_search(session, artifact_ids)
            result = await session.execute(
                sql_delete(SessionArtifactRow).where(SessionArtifactRow.session_id == session_id)
            )
            return result.rowcount


artifact_storage = ArtifactStorage()

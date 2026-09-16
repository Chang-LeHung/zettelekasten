"""SQLAlchemy persistence for stable library tags and artifact assignments."""

from datetime import UTC, datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from zett_agent import new_uuid7

from ...models import TagListOptions
from ...schemas import ArtifactTagOut, TagOut, TagWrite
from ..database import session_scope
from ..models import ArtifactTagModel, TagModel
from ..storage import AsyncStorage


def _tag_out(model: TagModel) -> TagOut:
    return TagOut(
        id=model.id,
        path=model.path,
        normalized_path=model.normalized_path,
        name=model.name,
        parent_id=model.parent_id,
        description=model.description,
        color=model.color,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class TagStorage(AsyncStorage[TagWrite, TagOut, str, TagListOptions]):
    """Typed storage for the persistent tag taxonomy."""

    async def create(self, entity: TagWrite) -> TagOut:
        now = datetime.now(UTC)
        async with session_scope() as session:
            model = TagModel(
                id=new_uuid7(),
                **entity.model_dump(),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            try:
                await session.flush()
            except IntegrityError as error:
                raise ValueError(f"Tag path already exists: {entity.path}") from error
            return _tag_out(model)

    async def get(self, entity_id: str) -> TagOut | None:
        async with session_scope() as session:
            model = await session.get(TagModel, entity_id)
            return _tag_out(model) if model else None

    async def get_by_normalized_path(self, normalized_path: str) -> TagOut | None:
        async with session_scope() as session:
            model = await session.scalar(select(TagModel).where(TagModel.normalized_path == normalized_path))
            return _tag_out(model) if model else None

    async def update(self, entity_id: str, entity: TagWrite) -> TagOut:
        async with session_scope() as session:
            model = await session.get(TagModel, entity_id)
            if model is None:
                raise KeyError(f"Tag not found: {entity_id}")
            for key, value in entity.model_dump().items():
                setattr(model, key, value)
            model.updated_at = datetime.now(UTC)
            try:
                await session.flush()
            except IntegrityError as error:
                raise ValueError(f"Tag path already exists: {entity.path}") from error
            return _tag_out(model)

    async def delete(self, entity_id: str) -> bool:
        async with session_scope() as session:
            model = await session.get(TagModel, entity_id)
            if model is None:
                return False
            await session.execute(sql_delete(ArtifactTagModel).where(ArtifactTagModel.tag_id == entity_id))
            await session.delete(model)
            return True

    async def list(self, options: TagListOptions | None = None) -> list[TagOut]:
        options = options or TagListOptions()
        async with session_scope() as session:
            statement = select(TagModel)
            if options.prefix:
                statement = statement.where(
                    (TagModel.normalized_path == options.prefix)
                    | TagModel.normalized_path.startswith(f"{options.prefix}/")
                )
            statement = statement.order_by(TagModel.normalized_path).limit(options.limit).offset(options.offset)
            return [_tag_out(model) for model in await session.scalars(statement)]

    async def replace_artifact_tags(self, artifact_id: str, tag_ids: tuple[str, ...]) -> None:
        """Atomically replace every confirmed tag assignment for one artifact."""
        async with session_scope() as session:
            await session.execute(sql_delete(ArtifactTagModel).where(ArtifactTagModel.artifact_id == artifact_id))
            now = datetime.now(UTC)
            for tag_id in dict.fromkeys(tag_ids):
                if await session.get(TagModel, tag_id) is None:
                    raise KeyError(f"Tag not found: {tag_id}")
                session.add(ArtifactTagModel(id=new_uuid7(), artifact_id=artifact_id, tag_id=tag_id, created_at=now))

    async def tags_for_artifacts(self, artifact_ids: tuple[str, ...]) -> dict[str, list[ArtifactTagOut]]:
        if not artifact_ids:
            return {}
        async with session_scope() as session:
            result = await session.execute(
                select(ArtifactTagModel.artifact_id, TagModel.id, TagModel.path, TagModel.name)
                .join(TagModel, TagModel.id == ArtifactTagModel.tag_id)
                .where(ArtifactTagModel.artifact_id.in_(artifact_ids))
                .order_by(TagModel.normalized_path)
            )
            rows = result.all()
        grouped: dict[str, list[ArtifactTagOut]] = {}
        for artifact_id, tag_id, path, name in rows:
            grouped.setdefault(artifact_id, []).append(ArtifactTagOut(id=tag_id, path=path, name=name))
        return grouped

    async def assignments(self) -> dict[str, set[str]]:
        """Return directly assigned artifact UUIDs keyed by tag UUID."""
        async with session_scope() as session:
            rows = (await session.execute(select(ArtifactTagModel.tag_id, ArtifactTagModel.artifact_id))).all()
        result: dict[str, set[str]] = {}
        for tag_id, artifact_id in rows:
            result.setdefault(tag_id, set()).add(artifact_id)
        return result

    async def child_count(self, tag_id: str) -> int:
        async with session_scope() as session:
            count = await session.scalar(select(func.count()).select_from(TagModel).where(TagModel.parent_id == tag_id))
            return count or 0

    async def assignment_count(self, tag_id: str) -> int:
        async with session_scope() as session:
            return (
                await session.scalar(
                    select(func.count()).select_from(ArtifactTagModel).where(ArtifactTagModel.tag_id == tag_id)
                )
                or 0
            )

    async def delete_artifact(self, artifact_id: str) -> int:
        async with session_scope() as session:
            result = await session.execute(
                sql_delete(ArtifactTagModel).where(ArtifactTagModel.artifact_id == artifact_id)
            )
            return result.rowcount

    async def delete_artifacts(self, artifact_ids: tuple[str, ...]) -> int:
        if not artifact_ids:
            return 0
        async with session_scope() as session:
            result = await session.execute(
                sql_delete(ArtifactTagModel).where(ArtifactTagModel.artifact_id.in_(artifact_ids))
            )
            return result.rowcount


tag_storage = TagStorage()

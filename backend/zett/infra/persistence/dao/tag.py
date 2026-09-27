"""SQLAlchemy persistence for the library taxonomy and the resources it classifies.

One ``tag_links`` table carries every assignment, and ``target_type`` says
whether the row classifies an artifact or a static asset. Storage here never
checks that the target exists: the service above is what knows which resource a
caller meant, and it refuses a link to something that is not there before this
layer writes one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from zett_agent.ids import new_uuid7

from ...._compat import UTC
from ....schemas import TagEntity, TagListOptions, TagRefEntity, TagTargetType, TagWrite
from ..database import session_scope
from ..storage import AsyncStorage
from ..tables import TARGET_TO_CODE, TagLinkRow, TagRow


def _tag_out(model: TagRow) -> TagEntity:
    return TagEntity(
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


class TagStorage(AsyncStorage[TagWrite, TagEntity, str, TagListOptions]):
    """Typed storage for the persistent tag taxonomy."""

    async def create(self, entity: TagWrite) -> TagEntity:
        now = datetime.now(UTC)
        async with session_scope() as session:
            model = TagRow(
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

    async def get(self, entity_id: str) -> TagEntity | None:
        async with session_scope() as session:
            model = await session.get(TagRow, entity_id)
            return _tag_out(model) if model else None

    async def get_by_normalized_path(self, normalized_path: str) -> TagEntity | None:
        async with session_scope() as session:
            model = await session.scalar(select(TagRow).where(TagRow.normalized_path == normalized_path))
            return _tag_out(model) if model else None

    async def update(self, entity_id: str, entity: TagWrite) -> TagEntity:
        async with session_scope() as session:
            model = await session.get(TagRow, entity_id)
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
            model = await session.get(TagRow, entity_id)
            if model is None:
                return False
            await session.execute(sql_delete(TagLinkRow).where(TagLinkRow.tag_id == entity_id))
            await session.delete(model)
            return True

    async def list(self, options: TagListOptions | None = None) -> list[TagEntity]:
        options = options or TagListOptions()
        async with session_scope() as session:
            statement = select(TagRow)
            if options.prefix:
                statement = statement.where(
                    (TagRow.normalized_path == options.prefix) | TagRow.normalized_path.startswith(f"{options.prefix}/")
                )
            statement = statement.order_by(TagRow.normalized_path).limit(options.limit).offset(options.offset)
            return [_tag_out(model) for model in await session.scalars(statement)]

    async def replace_tags(self, target_type: TagTargetType, target_id: str, tag_ids: tuple[str, ...]) -> None:
        """Atomically replace every assignment one resource carries.

        The delete and the inserts commit together, so a failure while resolving
        a tag leaves the resource with the assignments it already had.
        """
        code = int(TARGET_TO_CODE[target_type])
        async with session_scope() as session:
            await session.execute(
                sql_delete(TagLinkRow).where(
                    TagLinkRow.target_type == code,
                    TagLinkRow.target_id == target_id,
                )
            )
            now = datetime.now(UTC)
            for tag_id in dict.fromkeys(tag_ids):
                if await session.get(TagRow, tag_id) is None:
                    raise KeyError(f"Tag not found: {tag_id}")
                session.add(
                    TagLinkRow(
                        id=new_uuid7(),
                        target_type=code,
                        target_id=target_id,
                        tag_id=tag_id,
                        created_at=now,
                    )
                )

    async def tags_for(
        self,
        target_type: TagTargetType,
        target_ids: tuple[str, ...],
    ) -> dict[str, list[TagRefEntity]]:
        """Return the tags each of these resources carries, keyed by resource id."""
        if not target_ids:
            return {}
        code = int(TARGET_TO_CODE[target_type])
        async with session_scope() as session:
            result = await session.execute(
                select(TagLinkRow.target_id, TagRow.id, TagRow.path, TagRow.name)
                .join(TagRow, TagRow.id == TagLinkRow.tag_id)
                .where(TagLinkRow.target_type == code, TagLinkRow.target_id.in_(target_ids))
                .order_by(TagRow.normalized_path)
            )
            rows = result.all()
        grouped: dict[str, list[TagRefEntity]] = {}
        for target_id, tag_id, path, name in rows:
            grouped.setdefault(target_id, []).append(TagRefEntity(id=tag_id, path=path, name=name))
        return grouped

    async def assignments(self) -> dict[str, set[str]]:
        """Return the directly assigned resource UUIDs keyed by tag UUID.

        Artifacts and static assets share the key space because the tree counts
        everything one tag classifies; a target id is a UUID either way, so the
        two kinds cannot collide.
        """
        async with session_scope() as session:
            rows = (await session.execute(select(TagLinkRow.tag_id, TagLinkRow.target_id))).all()
        result: dict[str, set[str]] = {}
        for tag_id, target_id in rows:
            result.setdefault(tag_id, set()).add(target_id)
        return result

    async def child_count(self, tag_id: str) -> int:
        async with session_scope() as session:
            count = await session.scalar(select(func.count()).select_from(TagRow).where(TagRow.parent_id == tag_id))
            return count or 0

    async def assignment_count(self, tag_id: str) -> int:
        async with session_scope() as session:
            return (
                await session.scalar(select(func.count()).select_from(TagLinkRow).where(TagLinkRow.tag_id == tag_id))
                or 0
            )

    async def delete_links(self, target_type: TagTargetType, target_id: str) -> int:
        """Remove every assignment one resource carried, for its own delete."""
        code = int(TARGET_TO_CODE[target_type])
        async with session_scope() as session:
            result = await session.execute(
                sql_delete(TagLinkRow).where(
                    TagLinkRow.target_type == code,
                    TagLinkRow.target_id == target_id,
                )
            )
            return result.rowcount

    async def delete_target_links(self, target_type: TagTargetType, target_ids: tuple[str, ...]) -> int:
        """Remove the assignments of several resources of one kind at once."""
        if not target_ids:
            return 0
        code = int(TARGET_TO_CODE[target_type])
        async with session_scope() as session:
            result = await session.execute(
                sql_delete(TagLinkRow).where(
                    TagLinkRow.target_type == code,
                    TagLinkRow.target_id.in_(target_ids),
                )
            )
            return result.rowcount


tag_storage = TagStorage()

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import SortDirection, TagListOptions, TagSortField
from ..schemas import TagCreate, TagOut
from .database import session_scope
from .models import TagModel, card_tags_table
from .storage import Storage


def _tag_path(session: Session, tag: TagModel) -> str:
    """Resolve a display path by following parent IDs without ORM relationships."""
    names = [tag.name]
    parent_id = tag.parent_id
    visited_ids = {tag.id}
    while parent_id is not None and parent_id not in visited_ids:
        visited_ids.add(parent_id)
        parent = session.get(TagModel, parent_id)
        if parent is None:
            break
        names.append(parent.name)
        parent_id = parent.parent_id
    return "/".join(reversed(names))


def _card_counts(session: Session) -> dict[int, int]:
    """Load direct card counts for all tags with one typed aggregate query."""
    statement = select(card_tags_table.c.tag_id, func.count()).group_by(card_tags_table.c.tag_id)
    return {tag_id: count for tag_id, count in session.execute(statement)}


def _tag_out(session: Session, tag: TagModel, card_count: int = 0) -> TagOut:
    """Hydrate one ORM tag into the typed read model exposed by storage."""
    return TagOut(
        id=tag.id,
        name=tag.name,
        parent_id=tag.parent_id,
        description=tag.description,
        color=tag.color,
        created_at=tag.created_at,
        path=_tag_path(session, tag),
        card_count=card_count,
        children=[],
    )


def _descendant_ids(tags: list[TagModel], ancestor_id: int) -> set[int]:
    """Collect descendants from an in-memory parent index without database recursion."""
    children_by_parent: dict[int, list[int]] = {}
    for tag in tags:
        if tag.parent_id is not None:
            children_by_parent.setdefault(tag.parent_id, []).append(tag.id)
    descendants: set[int] = set()
    pending = list(children_by_parent.get(ancestor_id, []))
    while pending:
        tag_id = pending.pop()
        if tag_id in descendants:
            continue
        descendants.add(tag_id)
        pending.extend(children_by_parent.get(tag_id, []))
    return descendants


def _sort_tags(tags: list[TagOut], options: TagListOptions) -> None:
    """Apply the requested stable ordering to hydrated tags."""
    reverse = options.sort_direction == SortDirection.DESC
    if options.sort_by == TagSortField.CARD_COUNT:
        tags.sort(key=lambda tag: (tag.card_count, tag.name.casefold()), reverse=reverse)
    elif options.sort_by == TagSortField.CREATED_AT:
        tags.sort(key=lambda tag: (tag.created_at, tag.name.casefold()), reverse=reverse)
    else:
        tags.sort(key=lambda tag: tag.name.casefold(), reverse=reverse)


class TagStorage(Storage[TagCreate, TagOut, int, TagListOptions]):
    """SQLAlchemy implementation of the generic hierarchical tag storage contract."""

    def create(self, entity: TagCreate) -> TagOut:
        with session_scope() as session:
            self._require_parent(session, entity.parent_id)
            self._require_unique_name(session, entity.name, entity.parent_id)
            model = TagModel(
                name=entity.name,
                parent_id=entity.parent_id,
                description=entity.description,
                color=entity.color,
                created_at=datetime.now(UTC),
            )
            session.add(model)
            session.flush()
            return _tag_out(session, model)

    def get(self, entity_id: int) -> TagOut | None:
        with session_scope() as session:
            model = session.get(TagModel, entity_id)
            if model is None:
                return None
            card_count = session.scalar(
                select(func.count()).select_from(card_tags_table).where(card_tags_table.c.tag_id == entity_id)
            )
            return _tag_out(session, model, card_count or 0)

    def update(self, entity_id: int, entity: TagCreate) -> TagOut:
        with session_scope() as session:
            model = session.get(TagModel, entity_id)
            if model is None:
                raise HTTPException(404, "Tag not found")
            self._require_parent(session, entity.parent_id)
            all_tags = list(session.scalars(select(TagModel)))
            if entity.parent_id == entity_id or entity.parent_id in _descendant_ids(all_tags, entity_id):
                raise HTTPException(409, "A tag cannot be moved below itself or one of its descendants")
            self._require_unique_name(session, entity.name, entity.parent_id, exclude_id=entity_id)
            model.name = entity.name
            model.parent_id = entity.parent_id
            model.description = entity.description
            model.color = entity.color
            session.flush()
            card_count = session.scalar(
                select(func.count()).select_from(card_tags_table).where(card_tags_table.c.tag_id == entity_id)
            )
            return _tag_out(session, model, card_count or 0)

    def delete(self, entity_id: int) -> bool:
        with session_scope() as session:
            model = session.get(TagModel, entity_id)
            if model is None:
                return False
            children = session.scalars(select(TagModel).where(TagModel.parent_id == entity_id))
            for child in children:
                child.parent_id = model.parent_id
            session.execute(sql_delete(card_tags_table).where(card_tags_table.c.tag_id == entity_id))
            session.delete(model)
            return True

    def list(self, options: TagListOptions | None = None) -> list[TagOut]:
        options = options or TagListOptions()
        with session_scope() as session:
            models = list(session.scalars(select(TagModel)))
            counts = _card_counts(session)
            tags = [_tag_out(session, model, counts.get(model.id, 0)) for model in models]
            if options.query:
                needle = options.query.casefold()
                tags = [tag for tag in tags if needle in tag.name.casefold() or needle in tag.path.casefold()]

            model_ids = {model.id for model in models}
            if options.ancestor_id is not None:
                if options.ancestor_id not in model_ids:
                    return []
                selected_ids = {options.ancestor_id}
                if options.include_descendants:
                    selected_ids.update(_descendant_ids(models, options.ancestor_id))
                tags = [tag for tag in tags if tag.id in selected_ids]
            elif options.parent_id is not None:
                tags = [tag for tag in tags if tag.parent_id == options.parent_id]

            _sort_tags(tags, options)
            if not options.tree:
                return tags[options.offset : options.offset + options.limit]

            by_id = {tag.id: tag for tag in tags}
            roots: list[TagOut] = []
            for tag in tags:
                parent = by_id.get(tag.parent_id) if tag.parent_id is not None else None
                if parent is None:
                    roots.append(tag)
                else:
                    parent.children.append(tag)
            return roots[options.offset : options.offset + options.limit]

    @staticmethod
    def _require_parent(session: Session, parent_id: int | None) -> None:
        if parent_id is not None and session.get(TagModel, parent_id) is None:
            raise HTTPException(404, "Parent tag not found")

    @staticmethod
    def _require_unique_name(
        session: Session,
        name: str,
        parent_id: int | None,
        exclude_id: int | None = None,
    ) -> None:
        statement = select(TagModel.id).where(TagModel.name == name)
        statement = (
            statement.where(TagModel.parent_id.is_(None))
            if parent_id is None
            else statement.where(TagModel.parent_id == parent_id)
        )
        if exclude_id is not None:
            statement = statement.where(TagModel.id != exclude_id)
        if session.scalar(statement) is not None:
            raise HTTPException(409, "A tag with this name already exists under the parent")


tag_storage = TagStorage()

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, func, insert, or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.orm import Session

from ..models import CardListOptions
from ..schemas import CardCreate, CardOut
from .database import session_scope
from .models import CardModel, TagModel, card_tags_table
from .storage import Storage


def _tag_path(session: Session, tag: TagModel) -> str:
    names = [tag.name]
    parent_id = tag.parent_id
    while parent_id is not None:
        parent = session.get(TagModel, parent_id)
        if parent is None:
            break
        names.append(parent.name)
        parent_id = parent.parent_id
    return "/".join(reversed(names))


def _tag_out(session, tag: TagModel) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "parent_id": tag.parent_id,
        "description": tag.description,
        "color": tag.color,
        "created_at": tag.created_at,
        "path": _tag_path(session, tag),
        "card_count": session.scalar(
            select(func.count()).select_from(card_tags_table).where(card_tags_table.c.tag_id == tag.id)
        )
        or 0,
        "children": [],
    }


def _card_out(session, card: CardModel) -> CardOut:
    tag_ids = session.scalars(select(card_tags_table.c.tag_id).where(card_tags_table.c.card_id == card.id)).all()
    tags = list(session.scalars(select(TagModel).where(TagModel.id.in_(tag_ids)))) if tag_ids else []
    return CardOut.model_validate(
        {
            "id": card.id,
            "type": card.type,
            "title": card.title,
            "content": card.content,
            "raw_content": card.raw_content,
            "summary": card.summary,
            "source": card.source,
            "status": card.status,
            "created_at": card.created_at,
            "updated_at": card.updated_at,
            "tag_ids": tag_ids,
            "tags": [_tag_out(session, tag) for tag in tags],
        }
    )


def _descendant_ids(tag_id: int):
    descendants = select(TagModel.id).where(TagModel.id == tag_id).cte(f"tag_{tag_id}_descendants", recursive=True)
    children = select(TagModel.id).join(descendants, TagModel.parent_id == descendants.c.id)
    return select(descendants.c.id).union_all(children)


class CardStorage(Storage[CardCreate, CardOut, str, CardListOptions]):
    """SQLAlchemy implementation of the generic card storage contract."""

    def create(self, entity: CardCreate) -> CardOut:
        now = datetime.now(UTC)
        with session_scope() as session:
            card = CardModel(
                id=str(uuid4()),
                type=entity.type,
                title=entity.title,
                content=entity.content,
                raw_content=entity.raw_content,
                summary=entity.summary,
                source=entity.source,
                created_at=now,
                updated_at=now,
            )
            session.add(card)
            session.flush()
            if entity.tag_ids:
                session.execute(
                    insert(card_tags_table), [{"card_id": card.id, "tag_id": tag_id} for tag_id in set(entity.tag_ids)]
                )
            return _card_out(session, card)

    def get(self, entity_id: str) -> CardOut | None:
        with session_scope() as session:
            card = session.get(CardModel, entity_id)
            if card is None:
                return None
            return _card_out(session, card)

    def update(self, entity_id: str, entity: CardCreate) -> CardOut:
        with session_scope() as session:
            card = session.get(CardModel, entity_id)
            if card is None:
                raise KeyError(f"Card not found: {entity_id}")
            card.type, card.title, card.content = entity.type, entity.title, entity.content
            card.raw_content, card.summary, card.source = entity.raw_content, entity.summary, entity.source
            card.updated_at = datetime.now(UTC)
            session.flush()
            session.execute(sql_delete(card_tags_table).where(card_tags_table.c.card_id == entity_id))
            if entity.tag_ids:
                session.execute(
                    insert(card_tags_table),
                    [{"card_id": entity_id, "tag_id": tag_id} for tag_id in set(entity.tag_ids)],
                )
            return _card_out(session, card)

    def delete(self, entity_id: str) -> bool:
        with session_scope() as session:
            card = session.get(CardModel, entity_id)
            if card is None:
                return False
            session.execute(sql_delete(card_tags_table).where(card_tags_table.c.card_id == entity_id))
            session.delete(card)
            return True

    def list(self, options: CardListOptions | None = None) -> list[CardOut]:
        options = options or CardListOptions()
        with session_scope() as session:
            statement = select(CardModel).distinct()
            predicates = []
            if options.query:
                pattern = f"%{options.query}%"
                predicates.append(
                    or_(
                        CardModel.title.ilike(pattern),
                        CardModel.content.ilike(pattern),
                        CardModel.summary.ilike(pattern),
                    )
                )
            if options.resolved_card_types:
                predicates.append(CardModel.type.in_(options.resolved_card_types))
            if options.statuses:
                predicates.append(CardModel.status.in_(options.statuses))
            if options.source:
                predicates.append(CardModel.source.ilike(f"%{options.source}%"))
            if options.created_from:
                predicates.append(CardModel.created_at >= options.created_from)
            if options.created_to:
                predicates.append(CardModel.created_at <= options.created_to)
            if options.updated_from:
                predicates.append(CardModel.updated_at >= options.updated_from)
            if options.updated_to:
                predicates.append(CardModel.updated_at <= options.updated_to)
            if options.has_summary is not None:
                predicates.append(
                    CardModel.summary.is_not(None) if options.has_summary else CardModel.summary.is_(None)
                )
            for tag_id in options.resolved_include_tag_ids:
                tag_query = (
                    _descendant_ids(tag_id)
                    if options.include_descendants
                    else select(TagModel.id).where(TagModel.id == tag_id)
                )
                predicates.append(
                    CardModel.id.in_(select(card_tags_table.c.card_id).where(card_tags_table.c.tag_id.in_(tag_query)))
                )
            for tag_id in options.exclude_tag_ids:
                tag_query = (
                    _descendant_ids(tag_id)
                    if options.include_descendants
                    else select(TagModel.id).where(TagModel.id == tag_id)
                )
                predicates.append(
                    ~CardModel.id.in_(select(card_tags_table.c.card_id).where(card_tags_table.c.tag_id.in_(tag_query)))
                )
            order_column = getattr(CardModel, options.sort_by.value)
            if predicates:
                statement = statement.where(and_(*predicates))
            statement = statement.order_by(
                order_column.desc() if options.sort_direction.value == "desc" else order_column
            )
            statement = statement.limit(options.limit).offset(options.offset)
            return [_card_out(session, card) for card in session.scalars(statement).all()]


card_storage = CardStorage()

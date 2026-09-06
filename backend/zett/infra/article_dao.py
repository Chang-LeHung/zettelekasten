import json
from datetime import UTC, datetime
from enum import IntEnum
from uuid import uuid4

from sqlalchemy import or_, select

from ..models import ArticleListOptions
from ..schemas import ArticleCreate, ArticleOut, ArticleStatus
from .database import session_scope
from .models import ArticleModel
from .storage import Storage


class ArticleStatusCode(IntEnum):
    """Integer values used to persist finite article lifecycle states."""

    ACTIVE = 1


STATUS_TO_CODE = {ArticleStatus.ACTIVE: ArticleStatusCode.ACTIVE}
CODE_TO_STATUS = {int(code): status for status, code in STATUS_TO_CODE.items()}


def _article_out(model: ArticleModel) -> ArticleOut:
    """Hydrate a typed article read model from one SQLAlchemy record."""
    try:
        tag_paths = json.loads(model.tag_paths_json)
    except json.JSONDecodeError:
        tag_paths = []
    return ArticleOut(
        id=model.id,
        title=model.title,
        subtitle=model.subtitle,
        summary=model.summary,
        content=model.content,
        raw_content=model.raw_content,
        tag_paths=tag_paths,
        status=CODE_TO_STATUS[model.status],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class ArticleStorage(Storage[ArticleCreate, ArticleOut, str, ArticleListOptions]):
    """SQLAlchemy storage for permanent long-form Markdown articles."""

    def create(self, entity: ArticleCreate) -> ArticleOut:
        now = datetime.now(UTC)
        with session_scope() as session:
            model = ArticleModel(
                id=str(uuid4()),
                title=entity.title,
                subtitle=entity.subtitle,
                summary=entity.summary,
                content=entity.content,
                raw_content=entity.raw_content,
                tag_paths_json=json.dumps(entity.tag_paths, ensure_ascii=False),
                status=int(ArticleStatusCode.ACTIVE),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            return _article_out(model)

    def get(self, entity_id: str) -> ArticleOut | None:
        with session_scope() as session:
            model = session.get(ArticleModel, entity_id)
            return _article_out(model) if model else None

    def update(self, entity_id: str, entity: ArticleCreate) -> ArticleOut:
        with session_scope() as session:
            model = session.get(ArticleModel, entity_id)
            if model is None:
                raise KeyError(f"Article not found: {entity_id}")
            model.title = entity.title
            model.subtitle = entity.subtitle
            model.summary = entity.summary
            model.content = entity.content
            model.raw_content = entity.raw_content
            model.tag_paths_json = json.dumps(entity.tag_paths, ensure_ascii=False)
            model.updated_at = datetime.now(UTC)
            session.flush()
            return _article_out(model)

    def delete(self, entity_id: str) -> bool:
        with session_scope() as session:
            model = session.get(ArticleModel, entity_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def list(self, options: ArticleListOptions | None = None) -> list[ArticleOut]:
        options = options or ArticleListOptions()
        with session_scope() as session:
            statement = select(ArticleModel)
            if options.query:
                pattern = f"%{options.query}%"
                statement = statement.where(
                    or_(
                        ArticleModel.title.ilike(pattern),
                        ArticleModel.subtitle.ilike(pattern),
                        ArticleModel.summary.ilike(pattern),
                        ArticleModel.content.ilike(pattern),
                    )
                )
            if options.statuses:
                status_codes = [int(STATUS_TO_CODE[ArticleStatus(value)]) for value in options.statuses]
                statement = statement.where(ArticleModel.status.in_(status_codes))
            statement = statement.order_by(ArticleModel.updated_at.desc()).limit(options.limit).offset(options.offset)
            return [_article_out(model) for model in session.scalars(statement)]


article_storage = ArticleStorage()

import pytest
from sqlalchemy import select

from zett.infra import database
from zett.infra.dao.artifact import artifact_storage
from zett.infra.dao.session import session_storage
from zett.infra.models import SessionArtifactModel
from zett.infra.storage import Storage
from zett.models import ArtifactListOptions
from zett.schemas import (
    AgentArtifactWrite,
    AgentSessionCreate,
    ArticleArtifactContent,
    ArtifactStatus,
    CardArtifactContent,
    ImageArtifactContent,
)


def test_artifact_storage_persists_multiple_typed_outputs_per_session() -> None:
    session_id = session_storage.create(AgentSessionCreate()).session_id
    card = artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=CardArtifactContent(title="Small idea", content="A concise note.", card_type="idea"),
        )
    )
    article = artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ArticleArtifactContent(title="Long article", subtitle="A subtitle", content="# Body"),
        )
    )
    image = artifact_storage.create(
        AgentArtifactWrite(
            session_id=session_id,
            content=ImageArtifactContent(title="Architecture", prompt="A clean architecture diagram"),
        )
    )

    assert isinstance(artifact_storage, Storage)
    assert [item.id for item in artifact_storage.list(ArtifactListOptions(session_id=session_id))] == [
        card.id,
        article.id,
        image.id,
    ]
    assert article.content.artifact_type == "article"
    assert image.content.artifact_type == "image"
    with database.session_scope() as db:
        assert db.scalars(
            select(SessionArtifactModel.artifact_type).order_by(SessionArtifactModel.created_at)
        ).all() == [
            1,
            2,
            3,
        ]


def test_artifact_updates_are_versioned_and_cannot_cross_sessions() -> None:
    first_session = session_storage.create(AgentSessionCreate()).session_id
    second_session = session_storage.create(AgentSessionCreate()).session_id
    created = artifact_storage.create(
        AgentArtifactWrite(
            session_id=first_session,
            content=ArticleArtifactContent(title="Draft", content="First version"),
        )
    )
    updated = artifact_storage.update(
        created.id,
        AgentArtifactWrite(
            session_id=first_session,
            content=ArticleArtifactContent(title="Revised", content="Second version"),
            status=ArtifactStatus.SAVED,
        ),
    )

    assert updated.version == 2
    assert updated.status == ArtifactStatus.SAVED
    assert updated.content.title == "Revised"

    with pytest.raises(KeyError):
        artifact_storage.update(
            created.id,
            AgentArtifactWrite(
                session_id=second_session,
                content=ArticleArtifactContent(title="Wrong owner", content="Rejected"),
            ),
        )


def test_artifact_filters_and_explicit_session_cleanup() -> None:
    session_id = session_storage.create(AgentSessionCreate()).session_id
    artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=CardArtifactContent(title="Python", content="Code"))
    )
    artifact_storage.create(
        AgentArtifactWrite(session_id=session_id, content=ArticleArtifactContent(title="Python guide", content="Long"))
    )

    articles = artifact_storage.list(
        ArtifactListOptions(session_id=session_id, artifact_types=("article",), query="guide")
    )
    assert [item.content.title for item in articles] == ["Python guide"]
    assert artifact_storage.delete_session(session_id) == 2
    assert artifact_storage.list(ArtifactListOptions(session_id=session_id)) == []

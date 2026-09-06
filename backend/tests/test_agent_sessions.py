from datetime import UTC, datetime

from sqlalchemy import update
from zett_agent import UserMessage

from zett.application.services import KnowledgeWorkspaceApplicationService
from zett.infra import database
from zett.infra.agent_runtime import get_agent_runtime_storage
from zett.infra.agent_session_dao import agent_session_storage
from zett.infra.models import AgentSessionModel, Base
from zett.infra.storage import Storage
from zett.models import AgentSessionListOptions
from zett.schemas import AgentSessionCreate, AgentSessionTitleUpdate


def test_sessions_are_paginated_by_creation_time() -> None:
    assert isinstance(agent_session_storage, Storage)
    first = agent_session_storage.create(AgentSessionCreate(title="First"))
    second = agent_session_storage.create(AgentSessionCreate(title="Second"))
    third = agent_session_storage.create(AgentSessionCreate(title="Third"))
    created_times = {
        first.id: datetime(2024, 1, 1, tzinfo=UTC),
        second.id: datetime(2024, 1, 2, tzinfo=UTC),
        third.id: datetime(2024, 1, 3, tzinfo=UTC),
    }
    with database.session_scope() as session:
        for session_id, created_at in created_times.items():
            session.execute(
                update(AgentSessionModel).where(AgentSessionModel.id == session_id).values(created_at=created_at)
            )

    first_page = agent_session_storage.list(AgentSessionListOptions(limit=2, offset=0))
    second_page = agent_session_storage.list(AgentSessionListOptions(limit=2, offset=2))

    assert [session.title for session in first_page] == ["Third", "Second"]
    assert [session.title for session in second_page] == ["First"]


def test_user_title_update_finalizes_the_session_title() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    assert KnowledgeWorkspaceApplicationService.should_generate_session_title(session.id) is True

    updated = KnowledgeWorkspaceApplicationService.update_session_title(
        session.id,
        AgentSessionTitleUpdate(title="  Compaction design  "),
    )

    assert updated is not None
    assert updated.title == "Compaction design"
    assert updated.metadata["title_source"] == "user"
    assert updated.metadata["title_finalized"] is True
    assert KnowledgeWorkspaceApplicationService.should_generate_session_title(session.id) is False


async def test_session_history_is_owned_and_deleted_by_zett_agent() -> None:
    session = agent_session_storage.create(AgentSessionCreate())
    storage = get_agent_runtime_storage()
    await storage.append(session.id, "request-1", UserMessage(content="Persisted by zett-agent"))

    loaded = agent_session_storage.get(session.id)
    assert loaded is not None
    assert loaded.messages[0].content == "Persisted by zett-agent"
    assert "raw_messages" not in Base.metadata.tables
    assert "session_snapshots" not in Base.metadata.tables

    assert KnowledgeWorkspaceApplicationService.delete_session(session.id) == {"ok": True}
    assert storage.list_raw_messages(session.id) == []

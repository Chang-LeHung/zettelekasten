"""Session boundary backed exclusively by the standalone Agent database."""

from zett_agent import RawMessageRecord, SessionSummary

from ...models import SessionListOptions
from ...schemas import AgentSessionCreate
from ..agent_runtime import get_agent_runtime_storage
from ..storage import Storage
from .artifact import artifact_storage
from .asset import session_asset_storage


class SessionStorage(Storage[AgentSessionCreate, SessionSummary, str, SessionListOptions]):
    """Delegate session CRUD without duplicating Agent session tables.

    Deletion explicitly removes owned artifacts and assets before the Agent
    session and its history. The two databases and filesystem do not share a
    transaction; cleanup is idempotent so a failed deletion can be retried.
    """

    def create(self, entity: AgentSessionCreate) -> SessionSummary:
        return get_agent_runtime_storage().create_session(title=entity.title)

    def get(self, entity_id: str) -> SessionSummary | None:
        return get_agent_runtime_storage().get_session(entity_id)

    def update(self, entity_id: str, entity: AgentSessionCreate) -> SessionSummary:
        if entity.title is None:
            raise ValueError("Session title is required for an update")
        result = get_agent_runtime_storage().update_session(entity_id, title=entity.title)
        if result is None:
            raise KeyError(f"Session not found: {entity_id}")
        return result

    def delete(self, entity_id: str) -> bool:
        if self.get(entity_id) is None:
            return False
        # It's fine without consistency to delete artifacts and assets even if the session is already gone.
        res = get_agent_runtime_storage().delete_session(entity_id)
        artifact_storage.delete_session(entity_id)
        session_asset_storage.delete_session(entity_id)
        return res

    def list(self, options: SessionListOptions | None = None) -> list[SessionSummary]:
        options = options or SessionListOptions()
        return get_agent_runtime_storage().list_sessions(limit=options.limit, offset=options.offset)

    def list_raw_messages(self, session_id: str, *, limit: int = 100, offset: int = 0) -> list[RawMessageRecord]:
        """Read immutable history without assembling a workspace aggregate."""
        return get_agent_runtime_storage().list_raw_messages(session_id, limit=limit, offset=offset)

    def set_title_if_empty(self, session_id: str, title: str) -> bool:
        """Install one generated title without replacing user-owned text."""
        return get_agent_runtime_storage().set_session_title_if_empty(session_id, title)


session_storage = SessionStorage()

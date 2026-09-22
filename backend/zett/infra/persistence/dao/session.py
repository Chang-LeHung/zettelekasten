"""Session boundary backed exclusively by the standalone Agent database."""

from zett_agent import RawMessageRecord, SessionSummary

from ....application.assets.message_files import delete_session_files
from ....schemas import SESSION_TYPE_TO_CODE, AgentSessionCreate, SessionListOptions
from ...agent.runtime import get_agent_runtime_storage
from ..storage import AsyncStorage
from .artifact import artifact_storage
from .asset import session_asset_storage


class SessionStorage(AsyncStorage[AgentSessionCreate, SessionSummary, str, SessionListOptions]):
    """Delegate session CRUD without duplicating Agent session tables.

    The Agent database owns its own asynchronous connection pool, so these
    methods await storage directly instead of using the blocking adapter. The
    application database still exposes blocking DAOs, which are offloaded to
    threads here to keep the ASGI loop free.

    Deletion explicitly removes the Agent session and its history as well as the
    owned artifacts, asset files, and uploaded message images. The two databases
    and filesystem do not share a transaction; cleanup is idempotent so a failed
    deletion can be retried.
    """

    async def create(self, entity: AgentSessionCreate) -> SessionSummary:
        return await get_agent_runtime_storage().create_session(
            title=entity.title,
            session_type=SESSION_TYPE_TO_CODE[entity.session_type],
        )

    async def get(self, entity_id: str) -> SessionSummary | None:
        return await get_agent_runtime_storage().get_session(entity_id)

    async def update(self, entity_id: str, entity: AgentSessionCreate) -> SessionSummary:
        if entity.title is None:
            raise ValueError("Session title is required for an update")
        if await self.get(entity_id) is None:
            raise KeyError(f"Session not found: {entity_id}")
        result = await get_agent_runtime_storage().update_session(entity_id, title=entity.title)
        if result is None:
            raise KeyError(f"Session not found: {entity_id}")
        return result

    async def delete(self, entity_id: str) -> bool:
        if await self.get(entity_id) is None:
            return False
        result = await get_agent_runtime_storage().delete_session(entity_id)
        await artifact_storage.delete_session(entity_id)
        await session_asset_storage.delete_session(entity_id)
        # Asset rows and message uploads both live below the session directory.
        # Removing it whole also collects uploads that no row pointed at.
        await delete_session_files(entity_id)
        return result

    async def list(self, options: SessionListOptions | None = None) -> list[SessionSummary]:
        options = options or SessionListOptions()
        return await get_agent_runtime_storage().list_sessions(
            session_types=tuple(SESSION_TYPE_TO_CODE[value] for value in options.session_types) or None,
            limit=options.limit,
            offset=options.offset,
        )

    async def list_raw_messages(self, session_id: str, *, limit: int = 100, offset: int = 0) -> list[RawMessageRecord]:
        """Read immutable history without assembling a workspace aggregate."""
        return await get_agent_runtime_storage().list_raw_messages(session_id, limit=limit, offset=offset)


session_storage = SessionStorage()

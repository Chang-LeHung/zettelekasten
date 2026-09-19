"""Background orchestration for first-response conversation titles."""

from ..agent.model_factory import create_model
from ..agent.session_title import SessionTitleAgent
from ..infra.dao import session_storage
from ..infra.log import get_logger
from ..schemas import AgentSessionCreate, ProviderConnection

logger = get_logger(__name__)
DEFAULT_SESSION_TITLE = "新会话"


async def generate_initial_session_title(session_id: str, connection: ProviderConnection) -> None:
    """Generate a title after the first response while the session remains untitled."""
    try:
        session = await session_storage.get(session_id)
        if session is None or session.title not in (None, DEFAULT_SESSION_TITLE):
            return
        records = await session_storage.list_raw_messages(session_id, limit=10_000)
        if not records:
            return
        model = create_model(connection)
        try:
            title = await SessionTitleAgent(model).generate(records)
        finally:
            await model.aclose()
        if not title:
            return
        current = await session_storage.get(session_id)
        if current is not None and current.title in (None, DEFAULT_SESSION_TITLE):
            await session_storage.update(session_id, AgentSessionCreate(title=title))
    except Exception:
        # Title generation is intentionally best-effort and must never alter the
        # successful primary response already delivered to the user.
        logger.exception("Session title generation failed; session_id=%s", session_id)

"""Background orchestration for first-response conversation titles."""

from ..agent.model_factory import create_model
from ..agent.session_title import SessionTitleAgent
from ..infra.dao import session_storage
from ..infra.log import get_logger
from ..schemas import ProviderConnection
from .dependencies import run_sync

logger = get_logger(__name__)


async def generate_initial_session_title(session_id: str, connection: ProviderConnection) -> None:
    """Generate and atomically install a title when the session is still untitled."""
    try:
        session = await run_sync(session_storage.get, session_id)
        if session is None or session.title is not None:
            return
        records = await run_sync(session_storage.list_raw_messages, session_id, limit=10_000)
        if not records:
            return
        model = create_model(connection)
        try:
            title = await SessionTitleAgent(model).generate(records)
        finally:
            await model.aclose()
        if title:
            await run_sync(session_storage.set_title_if_empty, session_id, title)
    except Exception:
        # Title generation is intentionally best-effort and must never alter the
        # successful primary response already delivered to the user.
        logger.exception("Session title generation failed; session_id=%s", session_id)

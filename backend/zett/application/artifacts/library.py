"""The hidden session that owns artifacts created without a conversation.

Artifacts are session-owned by design: the table, the file layout below
``artifacts/<session_id>/``, the deletion cleanup, and the library query all
follow that ownership. Giving the CLI and scripts an owner keeps every one of
those rules true, and a ``SessionType.LIBRARY`` session is invisible to the
conversation sidebar because it only lists ``normal`` sessions.
"""

from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from ...infra.persistence.dao import KeyValueStorage, SessionStorage, key_value_storage, session_storage
from ...schemas import AgentSessionCreate, SessionType

#: Key-value key that records the owning session id.
LIBRARY_SESSION_KEY = "library:session"
LIBRARY_SESSION_TITLE = "Library"


class LibrarySessionService:
    """Find or create the session that owns artifacts created without one."""

    def __init__(
        self,
        *,
        sessions: SessionStorage | None = None,
        kv: KeyValueStorage | None = None,
    ) -> None:
        self._sessions = sessions or session_storage
        self._kv = kv or key_value_storage
        # A shared instance serves the application loop and the independent
        # loops tests create, so each loop gets its own creation lock.
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()

    def _lock(self) -> asyncio.Lock:
        """Return this loop's lock without binding any other loop."""
        return self._locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())

    async def get_or_create(self) -> str:
        """Return the library session id, creating that session at most once.

        The recorded id is trusted only while the session still exists, so a
        session deleted outside the API is replaced instead of leaving every
        later artifact creation failing.
        """
        async with self._lock():
            existing = await self.current()
            if existing is not None:
                return existing
            session = await self._sessions.create(
                AgentSessionCreate(title=LIBRARY_SESSION_TITLE, session_type=SessionType.LIBRARY)
            )
            await self._kv.update(LIBRARY_SESSION_KEY, session.session_id)
            return session.session_id

    async def current(self) -> str | None:
        """Return the recorded library session id while that session still exists.

        Callers that only need to recognize library-owned records — a deletion
        deciding whether an artifact is theirs to remove — must not create the
        session as a side effect of asking.
        """
        record = await self._kv.get(LIBRARY_SESSION_KEY)
        recorded = record.value if record is not None else None
        if isinstance(recorded, str) and await self._sessions.get(recorded) is not None:
            return recorded
        return None


library_session_service = LibrarySessionService()

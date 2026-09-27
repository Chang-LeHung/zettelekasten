"""Key-value persistence for shell commands approved by the user."""

import asyncio
from collections.abc import Iterable
from weakref import WeakKeyDictionary

from zett_agent.extensions.shell_approval import ShellApprovalMode

from ...schemas import JsonValue
from ..persistence.dao import KeyValueStorage, key_value_storage

ALLOWED_SHELL_COMMANDS_KEY = "shell_approval.allowed_commands"
SESSION_SHELL_APPROVAL_MODE_KEY_PREFIX = "shell_approval.session_mode."


class SQLiteShellApprovalStorage:
    """Persist an exact-command allowlist through the shared key-value storage."""

    def __init__(self, storage: KeyValueStorage = key_value_storage) -> None:
        self._storage = storage
        self._write_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()

    async def get_session_mode(self, session_id: str) -> ShellApprovalMode:
        """Return one session's persisted policy, defaulting to review."""
        record = await self._storage.get(_session_mode_key(session_id))
        if record is None or not isinstance(record.value, str):
            return ShellApprovalMode.REVIEW
        try:
            return ShellApprovalMode(record.value)
        except ValueError:
            return ShellApprovalMode.REVIEW

    async def set_session_mode(self, session_id: str, mode: ShellApprovalMode) -> None:
        """Persist one session's approval policy."""
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            raise ValueError("Session ID cannot be blank")
        await self._storage.update(
            _session_mode_key(normalized_session_id),
            ShellApprovalMode(mode).value,
        )

    async def clear_session_mode(self, session_id: str) -> None:
        """Remove one session's approval policy."""
        await self._storage.delete(_session_mode_key(session_id.strip()))

    async def is_allowed(self, session_id: str, command: str) -> bool:
        """Return whether session policy permits this exact normalized command."""
        if await self.get_session_mode(session_id) is ShellApprovalMode.ALLOW_ALL:
            return True
        normalized = _normalize_command(command)
        return normalized in set(await self._commands())

    async def allow_command(self, command: str) -> None:
        """Append one exact command to the persistent allowlist."""
        normalized = _normalize_command(command)
        async with self._write_lock():
            commands = dict.fromkeys((*await self._commands(), normalized))
            await self._storage.update(ALLOWED_SHELL_COMMANDS_KEY, list(commands))

    async def _commands(self) -> tuple[str, ...]:
        record = await self._storage.get(ALLOWED_SHELL_COMMANDS_KEY)
        if record is None:
            return ()
        return tuple(_string_values(record.value))

    def _write_lock(self) -> asyncio.Lock:
        return self._write_locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())


def _normalize_command(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        raise ValueError("Shell command cannot be blank")
    return normalized


def _session_mode_key(session_id: str) -> str:
    if not session_id:
        raise ValueError("Session ID cannot be blank")
    return f"{SESSION_SHELL_APPROVAL_MODE_KEY_PREFIX}{session_id}"


def _string_values(value: JsonValue) -> Iterable[str]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, str) and item.strip())


shell_approval_storage = SQLiteShellApprovalStorage()

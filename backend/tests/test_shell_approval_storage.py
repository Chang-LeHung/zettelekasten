"""Persistent shell approval allowlist behavior."""

import pytest
from zett_agent import ShellApprovalMode

from zett.infra.shell_approval import SQLiteShellApprovalStorage


async def test_shell_approval_storage_persists_exact_commands() -> None:
    storage = SQLiteShellApprovalStorage()

    assert await storage.is_allowed("session-a", "git status --short") is False
    await storage.allow_command("git status --short")
    await storage.allow_command("git status --short")

    assert await storage.is_allowed("session-a", "git status --short") is True
    assert await storage.is_allowed("session-a", "git diff --short") is False


async def test_shell_approval_storage_rejects_blank_commands() -> None:
    storage = SQLiteShellApprovalStorage()

    with pytest.raises(ValueError, match="cannot be blank"):
        await storage.allow_command("   ")


async def test_shell_approval_storage_persists_session_modes() -> None:
    storage = SQLiteShellApprovalStorage()

    assert await storage.get_session_mode("session-a") is ShellApprovalMode.REVIEW
    await storage.set_session_mode("session-a", ShellApprovalMode.ALLOW_ALL)
    await storage.set_session_mode("session-b", ShellApprovalMode.REVIEW)

    assert await storage.get_session_mode("session-a") is ShellApprovalMode.ALLOW_ALL
    assert await storage.get_session_mode("session-b") is ShellApprovalMode.REVIEW
    assert await storage.get_session_mode("session-c") is ShellApprovalMode.REVIEW
    assert await storage.is_allowed("session-a", "rm -rf temporary") is True
    assert await storage.is_allowed("session-b", "rm -rf temporary") is False

    await storage.clear_session_mode("session-a")
    assert await storage.get_session_mode("session-a") is ShellApprovalMode.REVIEW

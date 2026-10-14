"""Read models for the runtime's own update check and installation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UpdateStatus(BaseModel):
    """What this process knows about newer releases published on PyPI."""

    model_config = ConfigDict(extra="forbid")

    current: str = Field(description="Version this process is running")
    installed: str = Field(default="", description="Version installed on disk, which differs after an update")
    restart_required: bool = Field(default=False, description="Whether an installed update waits for a restart")
    latest: str | None = Field(default=None, description="Newest version PyPI offers")
    update_available: bool = Field(default=False, description="Whether latest is newer than installed")
    can_install: bool = Field(default=False, description="Whether this copy may install the update itself")
    detail: str = Field(default="", description="How the update would be installed, or why it cannot be")
    checked_at: datetime | None = Field(default=None, description="When PyPI was last asked")
    check_failed: bool = Field(default=False, description="Whether the newest check could not reach PyPI")


class UpdateInstallResult(BaseModel):
    """Outcome of asking the installer for one release."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    version: str
    needs_restart: bool = Field(default=True, description="Whether the running process still runs the old code")
    detail: str = ""
    output_tail: list[str] = Field(default_factory=list, description="Last lines the installer wrote")


class UpdateRestartResult(BaseModel):
    """Whether a restart of this server was handed to a detached helper."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    detail: str = ""

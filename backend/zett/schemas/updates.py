"""Read models for the runtime's own update check and installation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UpdateInstallKind(StrEnum):
    """How this running copy would install a newer release."""

    UV_TOOL = "uv-tool"
    PIPX = "pipx"
    PIP = "pip"
    CHECKOUT = "checkout"
    UNKNOWN = "unknown"


class UpdateStatus(BaseModel):
    """What this process knows about newer releases published on PyPI."""

    model_config = ConfigDict(extra="forbid")

    current: str = Field(description="Version this process is running")
    latest: str | None = Field(default=None, description="Newest version PyPI offers")
    update_available: bool = Field(default=False, description="Whether latest is newer than current")
    install_kind: UpdateInstallKind = Field(
        default=UpdateInstallKind.UNKNOWN,
        description="Installer that owns this copy",
    )
    can_install: bool = Field(default=False, description="Whether this copy may install the update itself")
    detail: str = Field(default="", description="How the update would be installed, or why it cannot be")
    checked_at: datetime | None = Field(default=None, description="When PyPI was last asked")
    check_failed: bool = Field(default=False, description="Whether the newest check could not reach PyPI")


class UpdateInstallResult(BaseModel):
    """Outcome of downloading one release and installing it."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    version: str
    needs_restart: bool = Field(default=True, description="Whether the running process still runs the old code")
    file: str | None = Field(default=None, description="Distribution file that was installed")
    detail: str = ""
    output_tail: list[str] = Field(default_factory=list, description="Last lines the installer wrote")

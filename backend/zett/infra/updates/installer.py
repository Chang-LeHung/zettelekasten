"""Find the installer that owns this copy, and let it install a release.

An update is installed by the same tool that installed Zett in the first place,
so the running copy is either replaced where it stands (`uv tool`, `pipx`, `pip`)
or refused, as a source checkout is, because that copy was never installed.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..log import get_logger
from ..scheduler import process_platform
from .pypi import PROJECT_NAME

logger = get_logger(__name__)

#: An installer downloads and resolves dependencies, so it gets room to finish.
INSTALL_TIMEOUT_SECONDS = 900

#: Lines of installer output kept for the answer the settings dialog shows.
OUTPUT_TAIL_LINES = 40


@dataclass(frozen=True)
class Installer:
    """How one running copy can be replaced by a newer release.

    ``command`` carries a ``{requirement}`` placeholder (``zettelekasten>=X``),
    and is ``None`` when this copy cannot install itself; ``detail`` says which
    installer it is, or why not. The requirement is a lower bound on purpose: a
    `uv tool` or pipx receipt records it, and a pinned ``==X`` would keep every
    later upgrade from moving past this release.
    """

    command: tuple[str, ...] | None = None
    detail: str = ""

    @property
    def can_install(self) -> bool:
        """Whether this copy may replace itself."""
        return self.command is not None


@dataclass(frozen=True)
class InstallOutcome:
    """What one installer run reported."""

    ok: bool
    detail: str
    output_tail: list[str] = field(default_factory=list)


def detect_installer(*, prefix: Path | None = None, package_root: Path | None = None) -> Installer:
    """Describe the installer that owns the interpreter running this process.

    ``package_root`` is the ``zett`` package directory; a repository layout
    around it means the copy was never installed and only its owner can update
    it, so the honest answer is a checkout instead of a pip command that would
    install a second copy somewhere else.
    """
    prefix = prefix if prefix is not None else Path(sys.prefix)
    package_root = package_root if package_root is not None else Path(__file__).resolve().parents[2]
    parts = prefix.parts
    if "uv" in parts and "tools" in parts:
        return Installer(
            ("uv", "tool", "install", "--force", "--refresh-package", PROJECT_NAME, "{requirement}"),
            "Installed by uv; the update runs `uv tool install --force` for the new release.",
        )
    if "pipx" in parts:
        return Installer(
            ("pipx", "install", "--force", "{requirement}"),
            "Installed by pipx; the update runs `pipx install --force` for the new release.",
        )
    if runs_from_checkout(package_root):
        return Installer(
            None,
            "This copy runs from a source checkout; update it with `git pull && make install`.",
        )
    return Installer(
        (sys.executable, "-m", "pip", "install", "--upgrade", "{requirement}"),
        "Installed by pip; the update runs `pip install --upgrade` for the new release.",
    )


def runs_from_checkout(package_root: Path) -> bool:
    """Whether this package is imported from a repository rather than a site."""
    backend = package_root.parent
    return (backend / "pyproject.toml").is_file() and (backend.parent / ".git").exists()


async def run_installer(installer: Installer, requirement: str) -> InstallOutcome:
    """Run one installer for a requirement and keep the tail of its output."""
    if installer.command is None:
        return InstallOutcome(False, installer.detail)
    command = [part.replace("{requirement}", requirement) for part in installer.command]
    logger.info("Installing %s with %s", requirement, " ".join(command))
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **process_platform.helper_process_kwargs(),
        )
    except OSError as error:
        return InstallOutcome(False, f"The installer could not start: {error}")
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=INSTALL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return InstallOutcome(False, f"The installer did not finish within {INSTALL_TIMEOUT_SECONDS}s")
    tail = stdout.decode("utf-8", "replace").splitlines()[-OUTPUT_TAIL_LINES:]
    ok = process.returncode == 0
    logger.info("Installer for %s exited with %s", requirement, process.returncode)
    return InstallOutcome(ok, "Installed" if ok else f"The installer exited with {process.returncode}", tail)

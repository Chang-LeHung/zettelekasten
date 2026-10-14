"""Find the installer that owns this copy, and let it install a release.

An update is installed by the same tool that installed Zett in the first place,
so the running copy is either replaced where it stands (`uv tool`, `pipx`, `pip`)
or refused, as a source checkout is, because that copy was never installed.

The tool is recognised by the receipt it leaves in the environment
(``uv-receipt.toml``, ``pipx_metadata.json``), not by what the directory is
called: ``UV_TOOL_DIR`` and ``PIPX_HOME`` move the environment anywhere, and a
guess from the path would hand a uv environment, which has no pip, to pip.
An update also has to leave the environment as the user built it: the same
Python, and the extensions they installed beside Zett.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
import shutil
import sys
from collections.abc import Callable
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
    #: Tried when ``command`` did not deliver the release: it exited cleanly and
    #: nothing moved (an upgrade of an environment pinned to one version), or it
    #: failed outright (an option this installer's release no longer accepts).
    fallback: tuple[str, ...] | None = None

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


UV_RECEIPT = "uv-receipt.toml"
PIPX_RECEIPT = "pipx_metadata.json"

# The two keys of a uv receipt requirement that a `--with` argument can express.
_RECEIPT_NAME = re.compile(r"\bname\s*=\s*\"([^\"]+)\"")
_RECEIPT_SPECIFIER = re.compile(r"\bspecifier\s*=\s*\"([^\"]*)\"")


def detect_installer(
    *,
    prefix: Path | None = None,
    package_root: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    has_pip: Callable[[], bool] | None = None,
) -> Installer:
    """Describe the installer that owns the interpreter running this process.

    ``package_root`` is the ``zett`` package directory; a repository layout
    around it means the copy was never installed and only its owner can update
    it, so the honest answer is a checkout instead of a pip command that would
    install a second copy somewhere else.
    """
    prefix = prefix if prefix is not None else Path(sys.prefix)
    package_root = package_root if package_root is not None else Path(__file__).resolve().parents[2]
    pip_available = has_pip if has_pip is not None else pip_is_importable
    parts = prefix.parts
    if (prefix / UV_RECEIPT).is_file() or ("uv" in parts and "tools" in parts):
        uv = which("uv")
        if uv is None:
            return Installer(
                None,
                "Installed by uv, but `uv` is not on this process's PATH; update it with "
                "`uv tool install --force --refresh-package zettelekasten zettelekasten`.",
            )
        return Installer(
            # `upgrade` is uv's own way to update a tool: it keeps the Python, the packages
            # added with `--with`, and the options given at install time (a mirror's
            # `--index-url`), because it reads them from the receipt.
            # `--reinstall-package` is the option `upgrade` has for a fresh look at the index
            # (it implies a refresh of that package): `--refresh-package` is an error here.
            (uv, "tool", "upgrade", "--reinstall-package", PROJECT_NAME, PROJECT_NAME),
            "Installed by uv; the update runs `uv tool upgrade` for the new release.",
            # An environment installed as `zettelekasten==X` is pinned, and upgrading it is a
            # clean no-op. Reinstalling with a lower bound moves it, keeping what can be kept.
            fallback=(
                uv,
                "tool",
                "install",
                "--force",
                "--refresh-package",
                PROJECT_NAME,
                "--python",
                f"{sys.version_info.major}.{sys.version_info.minor}",
                *with_arguments(prefix),
                "{requirement}",
            ),
        )
    if (prefix / PIPX_RECEIPT).is_file() or "pipx" in parts:
        pipx = which("pipx")
        if pipx is None:
            return Installer(
                None,
                "Installed by pipx, but `pipx` is not on this process's PATH; update it with `pipx upgrade zettelekasten`.",
            )
        # `upgrade` keeps the Python and the packages injected into the environment,
        # which a forced reinstall would not.
        return Installer(
            (pipx, "upgrade", PROJECT_NAME),
            "Installed by pipx; the update runs `pipx upgrade` for the new release.",
        )
    if runs_from_checkout(package_root):
        return Installer(
            None,
            "This copy runs from a source checkout; update it with `git pull && make install`.",
        )
    if not pip_available():
        return Installer(
            None,
            "No installer owns this copy and its environment has no pip; update it with the tool that installed it.",
        )
    return Installer(
        (sys.executable, "-m", "pip", "install", "--upgrade", "{requirement}"),
        "Installed by pip; the update runs `pip install --upgrade` for the new release.",
    )


def pip_is_importable() -> bool:
    """Whether ``python -m pip`` can run in this interpreter's environment."""
    return importlib.util.find_spec("pip") is not None


def with_arguments(prefix: Path) -> tuple[str, ...]:
    """Name the packages a uv tool was given beside Zett, as ``--with`` arguments.

    uv keeps the whole requirement list in the receipt, the tool itself among
    them. An entry that is more than a name and a version bound (a path, a URL,
    a git source) cannot be repeated here and is logged, because losing an
    extension silently is the failure this exists to prevent.
    """
    try:
        text = (prefix / UV_RECEIPT).read_text(encoding="utf-8")
    except OSError:
        return ()
    block = re.search(r"requirements\s*=\s*\[(.*?)\n?\]\s*\n", text, re.DOTALL)
    if block is None:
        return ()
    arguments: list[str] = []
    skipped = 0
    for entry in re.findall(r"\{([^{}]*)\}", block.group(1)):
        named = _RECEIPT_NAME.search(entry)
        if named is None:
            skipped += 1
            continue
        name = named.group(1)
        if name.lower().replace("_", "-") == PROJECT_NAME:
            continue
        specifier = _RECEIPT_SPECIFIER.search(entry)
        leftover = _RECEIPT_NAME.sub("", entry)
        leftover = _RECEIPT_SPECIFIER.sub("", leftover).strip(" ,\n\t")
        if leftover:
            skipped += 1
            continue
        arguments.extend(("--with", f"{name}{specifier.group(1) if specifier else ''}"))
    if skipped:
        logger.warning("uv receipt names %d requirement(s) a reinstall cannot keep", skipped)
    return tuple(arguments)


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

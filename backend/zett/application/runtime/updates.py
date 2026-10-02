"""Report newer releases of this application, and install one on request.

The check is cached in the key-value store so opening Settings never waits for
the network, and an install is single-flight: it downloads the release file
first and only then runs the installer on that exact path, because the process
that starts the installer may itself be replaced while the installer works.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import re
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from ..._compat import UTC
from ...infra.log import get_logger
from ...infra.persistence.dao import KeyValueStorage, key_value_storage
from ...infra.updates import (
    Installer,
    InstallOutcome,
    PypiClient,
    PypiError,
    ReleaseInfo,
    detect_installer,
    run_installer,
)
from ...schemas import UpdateInstallResult, UpdateStatus

logger = get_logger(__name__)

#: The distribution this application ships as; the command it installs is `zett`.
DISTRIBUTION = "zettelekasten"

#: Where the last successful check is remembered between restarts.
STATUS_KEY = "updates.status"

#: How long one PyPI answer is reused before Settings asks again.
CHECK_INTERVAL = timedelta(hours=6)

VERSION_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)")


def version_key(value: str) -> tuple[int, ...]:
    """Order two dotted versions; a pre-release suffix sorts as its release."""
    match = VERSION_PREFIX.match(value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def installed_version(distribution: str = DISTRIBUTION) -> str:
    """Return the version of the installed distribution, or ``0.0.0``."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        # A source checkout that was never installed has no metadata to read.
        return "0.0.0"


def _checked_at(value: object) -> datetime | None:
    """Parse one remembered timestamp, ignoring anything unreadable."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class UpdateService:
    """Answer what is installed, what PyPI offers, and install it on request."""

    def __init__(
        self,
        *,
        client: PypiClient | None = None,
        storage: KeyValueStorage = key_value_storage,
        installer_factory: Callable[[], Installer] = detect_installer,
        runner: Callable[[Installer, Path], object] = run_installer,
        interval: timedelta = CHECK_INTERVAL,
        distribution: str = DISTRIBUTION,
    ) -> None:
        self._client = client or PypiClient()
        self._storage = storage
        self._installer_factory = installer_factory
        self._runner = runner
        self._interval = interval
        self._distribution = distribution
        # One install at a time: two of them would race for the same environment.
        self._install_lock = asyncio.Lock()

    async def status(self, *, refresh: bool = False) -> UpdateStatus:
        """Report the newest release, reusing the last check when it is fresh."""
        installer = self._installer_factory()
        current = installed_version(self._distribution)
        cached = None if refresh else await self._remembered()
        failure = ""
        if cached is None:
            try:
                release: ReleaseInfo = await self._client.latest_release()
            except PypiError as error:
                logger.info("Update check failed: %s", error)
                failure = str(error)
                latest, checked_at = None, None
            else:
                latest, checked_at = release.version, datetime.now(UTC)
                await self._storage.update(
                    STATUS_KEY,
                    {"version": latest, "checked_at": checked_at.isoformat()},
                )
        else:
            latest, checked_at = cached
        available = bool(latest) and version_key(latest) > version_key(current)
        return UpdateStatus(
            current=current,
            latest=latest,
            update_available=available,
            install_kind=installer.kind,
            can_install=installer.can_install and available,
            detail=failure or installer.detail,
            checked_at=checked_at,
            check_failed=bool(failure),
        )

    async def install(self, version: str) -> UpdateInstallResult:
        """Download one release and let this copy's installer install it."""
        installer = self._installer_factory()
        if not installer.can_install:
            return UpdateInstallResult(ok=False, version=version, detail=installer.detail)
        async with self._install_lock:
            try:
                release: ReleaseInfo = await self._client.latest_release()
                if version_key(release.version) != version_key(version):
                    return UpdateInstallResult(
                        ok=False,
                        version=version,
                        detail=f"PyPI now publishes {release.version}; check for updates again",
                    )
                file = release.best()
                if file is None:
                    return UpdateInstallResult(
                        ok=False,
                        version=version,
                        detail=f"PyPI publishes no files for {version}",
                    )
                with tempfile.TemporaryDirectory(prefix="zett-update-") as directory:
                    path = await self._client.download(file, Path(directory))
                    outcome: InstallOutcome = await self._runner(installer, path)  # type: ignore[assignment]
            except PypiError as error:
                return UpdateInstallResult(ok=False, version=version, detail=str(error))
        if not outcome.ok:
            logger.info("Installing %s failed: %s", version, outcome.detail)
        return UpdateInstallResult(
            ok=outcome.ok,
            version=version,
            needs_restart=outcome.ok,
            file=file.filename,
            detail=outcome.detail,
            output_tail=outcome.output_tail,
        )

    async def _remembered(self) -> tuple[str, datetime] | None:
        """Return the last check while it is still fresh enough to trust."""
        record = await self._storage.get(STATUS_KEY)
        value = record.value if record is not None and isinstance(record.value, dict) else {}
        version = str(value.get("version") or "")
        checked_at = _checked_at(value.get("checked_at"))
        if not version or checked_at is None:
            return None
        if datetime.now(UTC) - checked_at > self._interval:
            return None
        return version, checked_at


update_service = UpdateService()

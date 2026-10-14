"""Report newer releases of this application, and install one on request.

The check is cached in the key-value store so opening Settings never waits for
the network, and an install is single-flight: two installers would race for the
same environment. The installer that owns this copy resolves and verifies the
release from the index itself, because the process that starts it may be
replaced while it works.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timedelta

from ..._compat import UTC
from ...infra.log import get_logger
from ...infra.persistence.dao import KeyValueStorage, key_value_storage
from ...infra.updates import (
    PROJECT_NAME,
    Installer,
    InstallOutcome,
    PypiClient,
    PypiError,
    detect_installer,
    run_installer,
)
from ...schemas import UpdateInstallResult, UpdateStatus

logger = get_logger(__name__)

#: Where the last successful check is remembered between restarts.
STATUS_KEY = "updates.status"

#: How long one PyPI answer is reused before Settings asks again.
CHECK_INTERVAL = timedelta(hours=6)

#: What ``installed_version`` answers when no installed distribution can be found.
UNKNOWN_VERSION = "0.0.0"

VERSION_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)")


def version_key(value: str) -> tuple[int, ...]:
    """Order two dotted versions; a pre-release suffix sorts as its release."""
    match = VERSION_PREFIX.match(value.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def installed_version(distribution: str = PROJECT_NAME) -> str:
    """Return the version of the installed distribution, or ``0.0.0``."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        # A source checkout that was never installed has no metadata to read.
        return UNKNOWN_VERSION


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
        runner: Callable[[Installer, str], Awaitable[InstallOutcome]] = run_installer,
        interval: timedelta = CHECK_INTERVAL,
        distribution: str = PROJECT_NAME,
        running_version: str | None = None,
    ) -> None:
        self._client = client or PypiClient()
        self._storage = storage
        self._installer_factory = installer_factory
        self._runner = runner
        self._interval = interval
        self._distribution = distribution
        # What this process imported: an installer rewrites the files on disk,
        # but only a restart changes the code that is running.
        self._running_version = running_version or installed_version(distribution)
        self._install_lock = asyncio.Lock()

    async def status(self, *, refresh: bool = False) -> UpdateStatus:
        """Report the newest release, reusing the last check when it is fresh."""
        installer = self._installer_factory()
        installed = installed_version(self._distribution)
        cached = None if refresh else await self._remembered()
        failure = ""
        if cached is None:
            try:
                latest = await self._client.latest_version()
            except PypiError as error:
                logger.info("Update check failed: %s", error)
                failure = str(error)
                latest, checked_at = None, None
            else:
                checked_at = datetime.now(UTC)
                await self._storage.update(
                    STATUS_KEY,
                    {"version": latest, "checked_at": checked_at.isoformat()},
                )
        else:
            latest, checked_at = cached
        # An environment replaced under a running process (another Python, a reinstall) takes
        # this copy's metadata with it: the process still runs, but no distribution is found.
        # That is a restart waiting to happen, not an uninstalled checkout.
        replaced = installed == UNKNOWN_VERSION and self._running_version != UNKNOWN_VERSION
        if replaced:
            installed = latest or self._running_version
        available = bool(latest) and version_key(latest) > version_key(installed)
        return UpdateStatus(
            current=self._running_version,
            installed=installed,
            restart_required=replaced or version_key(installed) > version_key(self._running_version),
            latest=latest,
            update_available=available,
            can_install=installer.can_install and available,
            detail=failure or installer.detail,
            checked_at=checked_at,
            check_failed=bool(failure),
        )

    async def install(self, version: str) -> UpdateInstallResult:
        """Let this copy's installer install ``version`` while it is still the newest."""
        installer = self._installer_factory()
        if not installer.can_install:
            return self._refused(version, installer.detail)
        if self._install_lock.locked():
            return self._refused(version, "An update is already being installed")
        async with self._install_lock:
            latest = version
            try:
                latest = await self._client.latest_version()
            except PypiError as error:
                # The check that offered this release already succeeded. Failing the install
                # on a second, slow lookup would turn a flaky link into "cannot update", and
                # the installer resolves the lower bound from the index itself.
                logger.info("Skipping the pre-install lookup: %s", error)
            else:
                if version_key(latest) != version_key(version):
                    return self._refused(version, f"PyPI now publishes {latest}; check for updates again")
            requirement = f"{self._distribution}>={latest}"
            outcome = await self._runner(installer, requirement)
            if outcome.ok:
                outcome = self._verified(outcome, latest)
            if not outcome.ok and installer.fallback is not None:
                # The first command did not deliver the release: a pinned environment makes an
                # upgrade a clean no-op, and an installer release that renamed an option fails
                # outright. Either way the reinstall that names the new bound is a second,
                # independent attempt, and its answer is the one worth showing.
                logger.info("The first installer did not deliver %s (%s); trying the fallback", latest, outcome.detail)
                again = replace(installer, command=installer.fallback, fallback=None)
                outcome = await self._runner(again, requirement)
                if outcome.ok:
                    outcome = self._verified(outcome, latest)
        if not outcome.ok:
            logger.info("Installing %s failed: %s", latest, outcome.detail)
        return UpdateInstallResult(
            ok=outcome.ok,
            version=latest,
            needs_restart=outcome.ok,
            detail=outcome.detail,
            output_tail=outcome.output_tail,
        )

    @staticmethod
    def _refused(version: str, detail: str) -> UpdateInstallResult:
        """Answer an install that never ran: nothing changed, so nothing needs a restart."""
        return UpdateInstallResult(ok=False, version=version, needs_restart=False, detail=detail)

    def _verified(self, outcome: InstallOutcome, latest: str) -> InstallOutcome:
        """Trust the disk over the installer's exit status.

        Some installers exit cleanly without moving (`pipx upgrade` when a mirror has
        not synced the release yet), and a restart would then promise a version that
        was never installed.
        """
        installed = installed_version(self._distribution)
        if version_key(installed) >= version_key(latest):
            return outcome
        return InstallOutcome(
            False,
            f"The installer finished, but {installed} is still installed; "
            f"{latest} may not be available from your package index yet.",
            outcome.output_tail,
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

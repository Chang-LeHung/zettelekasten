"""Read PyPI for the newest release of this product, and fetch one of its files.

The update check is the one outbound call Zett makes on its own behalf: it asks
the public JSON API for the newest version, and an install downloads the file
that API names, checking the sha256 PyPI recorded before an installer sees it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..log import get_logger

logger = get_logger(__name__)

#: The distribution this application ships as; the command it installs is `zett`.
PROJECT_NAME = "zettelekasten"

#: Reading the index is a background nicety, so it never waits long.
LOOKUP_TIMEOUT_SECONDS = 10.0
DOWNLOAD_TIMEOUT_SECONDS = 300.0


class PypiError(RuntimeError):
    """The index could not be read, or a release file could not be fetched."""


@dataclass(frozen=True)
class ReleaseFile:
    """One distribution file of a release, as PyPI describes it."""

    filename: str
    url: str
    sha256: str | None
    kind: str


@dataclass(frozen=True)
class ReleaseInfo:
    """The newest release PyPI publishes for this project."""

    version: str
    files: tuple[ReleaseFile, ...]

    def best(self) -> ReleaseFile | None:
        """Prefer a wheel: installing one needs no build step on the host."""
        wheel = next((file for file in self.files if file.kind == "wheel"), None)
        return wheel or (self.files[0] if self.files else None)


def _release_files(payload: dict[str, Any]) -> tuple[ReleaseFile, ...]:
    """Read the file list of one release, skipping entries without a URL."""
    files: list[ReleaseFile] = []
    for entry in payload.get("urls") or []:
        filename = str(entry.get("filename") or "")
        url = str(entry.get("url") or "")
        if not filename or not url:
            continue
        digests = entry.get("digests") or {}
        files.append(
            ReleaseFile(
                filename=filename,
                url=url,
                sha256=digests.get("sha256"),
                kind="wheel" if filename.endswith(".whl") else "sdist",
            )
        )
    return tuple(files)


class PypiClient:
    """Ask PyPI what the newest release is, and download one of its files."""

    def __init__(self, *, project: str = PROJECT_NAME, timeout: float = LOOKUP_TIMEOUT_SECONDS) -> None:
        self.project = project
        self.timeout = timeout
        self.url = f"https://pypi.org/pypi/{project}/json"

    async def latest_release(self) -> ReleaseInfo:
        """Return the newest published release, or refuse with a reason."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(self.url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise PypiError(f"PyPI lookup failed: {error}") from error
        version = str((payload.get("info") or {}).get("version") or "").strip()
        if not version:
            raise PypiError("PyPI answered without a version for this project")
        return ReleaseInfo(version=version, files=_release_files(payload))

    async def download(self, file: ReleaseFile, directory: Path) -> Path:
        """Download one release file into ``directory`` and verify its digest."""
        target = directory / file.filename
        digest = hashlib.sha256()
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
                async with client.stream("GET", file.url) as response:
                    response.raise_for_status()
                    with target.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            digest.update(chunk)
                            handle.write(chunk)
        except (httpx.HTTPError, OSError) as error:
            raise PypiError(f"Downloading {file.filename} failed: {error}") from error
        if file.sha256 and digest.hexdigest() != file.sha256:
            target.unlink(missing_ok=True)
            raise PypiError(f"{file.filename} does not match the sha256 PyPI published")
        logger.info("Downloaded %s (%s bytes) from PyPI", file.filename, target.stat().st_size)
        return target

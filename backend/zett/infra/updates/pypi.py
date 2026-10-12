"""Read PyPI for the newest release of this product.

The update check is the one outbound call Zett makes on its own behalf: it asks
the public JSON API which version is newest. Installing is left to the installer
that owns this copy, which resolves, downloads, and verifies the release from
the index itself, so the receipt it keeps names a requirement instead of a file
that no longer exists once the install is over.
"""

from __future__ import annotations

from ..log import get_logger

logger = get_logger(__name__)

#: The distribution this application ships as; the command it installs is `zett`.
PROJECT_NAME = "zettelekasten"

#: Reading the index is a background nicety, so it never waits long.
LOOKUP_TIMEOUT_SECONDS = 10.0


class PypiError(RuntimeError):
    """The index could not be read."""


class PypiClient:
    """Ask PyPI what the newest release is."""

    def __init__(self, *, project: str = PROJECT_NAME, timeout: float = LOOKUP_TIMEOUT_SECONDS) -> None:
        self.project = project
        self.timeout = timeout
        self.url = f"https://pypi.org/pypi/{project}/json"

    async def latest_version(self) -> str:
        """Return the newest published version, or refuse with a reason."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(self.url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise PypiError(f"PyPI lookup failed: {error}") from error
        info = payload.get("info") if isinstance(payload, dict) else None
        version = str(info.get("version") or "").strip() if isinstance(info, dict) else ""
        if not version:
            raise PypiError("PyPI answered without a version for this project")
        return version

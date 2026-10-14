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

#: Reading the index is a background nicety, but a slow link is not a broken one:
#: from some networks the TLS handshake alone takes five to ten seconds, so a
#: tighter budget reported a reachable index as down. The connection gets less
#: than the whole answer so a dead host still fails in reasonable time.
LOOKUP_TIMEOUT_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 20.0

#: One more try after a timeout or a dropped connection: those are the failures
#: a second attempt routinely fixes, and the answer is cached for hours.
LOOKUP_ATTEMPTS = 2


class PypiError(RuntimeError):
    """The index could not be read."""


class PypiClient:
    """Ask PyPI what the newest release is."""

    def __init__(
        self,
        *,
        project: str = PROJECT_NAME,
        timeout: float = LOOKUP_TIMEOUT_SECONDS,
        attempts: int = LOOKUP_ATTEMPTS,
    ) -> None:
        self.project = project
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self.url = f"https://pypi.org/pypi/{project}/json"

    async def latest_version(self) -> str:
        """Return the newest published version, or refuse with a reason."""
        payload = await self._fetch()
        info = payload.get("info") if isinstance(payload, dict) else None
        version = str(info.get("version") or "").strip() if isinstance(info, dict) else ""
        if not version:
            raise PypiError("PyPI answered without a version for this project")
        return version

    async def _fetch(self) -> object:
        """Read the project's JSON document, trying again after a transient failure."""
        import httpx

        timeout = httpx.Timeout(self.timeout, connect=min(CONNECT_TIMEOUT_SECONDS, self.timeout))
        failure: Exception | None = None
        for _ in range(self.attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.get(self.url)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as error:
                # The index answered; asking again would get the same answer.
                raise PypiError(f"PyPI lookup failed: {describe(error)}") from error
            except (httpx.HTTPError, ValueError) as error:
                failure = error
                logger.info("PyPI lookup attempt failed: %s", describe(error))
        raise PypiError(f"PyPI lookup failed: {describe(failure)}") from failure


def describe(error: BaseException | None) -> str:
    """Name an error for a person: a timeout's own message is empty, its type is not."""
    if error is None:
        return "unknown error"
    message = str(error).strip()
    kind = type(error).__name__
    return f"{kind}: {message}" if message else kind

"""Stable object-store contracts for every persisted file path.

Every stored path is an ObjectKey: a POSIX-style relative path below the
configured storage root. Physical layout, URL generation, and containment
checks belong to the object-store adapter rather than individual DAOs.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote


class InvalidObjectKey(ValueError):
    """Raised when a path cannot safely identify an object below storage_root."""


PUBLIC_OBJECT_PREFIXES = ("assets/", "artifacts/")


class ObjectKey:
    """One canonical relative object path such as ``assets/static/id.pdf``.

    Example:
        ``ObjectKey("assets/static/logo.png")`` is valid.
        ``ObjectKey("../logo.png")`` and ``ObjectKey("/tmp/logo.png")`` raise
        :class:`InvalidObjectKey`.
    """

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        if not value or value != value.strip() or value.startswith("/") or "\\" in value or "\x00" in value:
            raise InvalidObjectKey(f"Object key must be a non-empty relative POSIX path: {value!r}")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise InvalidObjectKey(f"Object key contains an unsafe path segment: {value!r}")
        self.value = value

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"ObjectKey({self.value!r})"


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Metadata returned after one object is written."""

    key: ObjectKey
    size_bytes: int
    sha256: str


class ObjectStore(Protocol):
    """Read, write, delete, and address objects without exposing storage details.

    Example:
        A local store rooted at ``~/.zettelekasten`` maps
        ``assets/static/logo.png`` to
        ``/Users/alice/.zettelekasten/assets/static/logo.png`` and exposes it as
        ``/api/files/assets/static/logo.png``.
    """

    @property
    def root(self) -> Path:
        """Absolute storage root shared by every object key."""

    def resolve(self, key: str | ObjectKey) -> Path:
        """Resolve one key to a safe absolute path.

        Example:
            ``store.resolve("assets/static/logo.png")`` returns the path below
            ``storage_root`` and rejects symlinks that escape that root.
        """

    def url(self, key: str | ObjectKey) -> str:
        """Return the one public URL used to read the object.

        Example:
            ``store.url("assets/static/logo.png")`` returns
            ``"/api/files/assets/static/logo.png"``.
        """

    async def write(self, key: str | ObjectKey, content: bytes) -> StoredObject:
        """Atomically expose bytes at one key and return their digest.

        Example:
            ``await store.write("assets/static/logo.png", png_bytes)`` returns
            a :class:`StoredObject` containing the key, byte length, and SHA-256.

        Implementations should write a temporary object in the destination
        directory and atomically replace the destination so readers never
        observe a partial object. Durability across a host crash is separate
        from this atomic-visibility guarantee.
        """

    async def read(self, key: str | ObjectKey) -> bytes:
        """Read complete object bytes.

        Example:
            ``await store.read("artifacts/session-1/paper/paper.pdf")`` returns
            the compiled PDF bytes.
        """

    async def delete(self, key: str | ObjectKey) -> bool:
        """Delete one object if it exists.

        Example:
            ``await store.delete("assets/static/logo.png")`` returns ``True``
            once, then ``False`` when the same key is deleted again.
        """

    async def exists(self, key: str | ObjectKey) -> bool:
        """Return whether one object currently exists.

        Example:
            ``await store.exists("assets/static/logo.png")`` reports whether
            that exact object key currently resolves to a file.
        """

    def ensure_directory(self, key: str | ObjectKey) -> Path:
        """Create and return one directory below the storage root.

        Example:
            ``store.ensure_directory("artifacts/session-1/paper")`` creates the
            project directory before the Agent writes LaTeX sources.
        """


def join_object_key(*parts: str) -> ObjectKey:
    """Build one canonical key from already-relative path fragments.

    Example:
        ``join_object_key("assets", "static", "logo.png")`` returns
        ``ObjectKey("assets/static/logo.png")``.
    """
    return ObjectKey("/".join(part.strip("/") for part in parts if part.strip("/")))


def session_asset_key(session_id: str, asset_id: str, suffix: str = "") -> ObjectKey:
    """Return the canonical key for one session-owned binary asset.

    Example:
        ``session_asset_key("session-1", "asset-1", ".png")`` returns
        ``assets/sessions/session-1/asset-1.png``.
    """
    return join_object_key("assets", "sessions", session_id, f"{asset_id}{suffix}")


def static_asset_key(asset_id: str, suffix: str = "") -> ObjectKey:
    """Return the canonical key for one session-independent uploaded asset.

    Example:
        ``static_asset_key("asset-1", ".pdf")`` returns
        ``assets/static/asset-1.pdf``.
    """
    return join_object_key("assets", "static", f"{asset_id}{suffix}")


def latex_project_key(session_id: str, project_name: str) -> ObjectKey:
    """Return the canonical directory key for one session-owned LaTeX project.

    Example:
        ``latex_project_key("session-1", "paper")`` returns
        ``artifacts/session-1/paper``.
    """
    return join_object_key("artifacts", session_id, project_name)


def object_url(key: str | ObjectKey) -> str:
    """Return the unified public URL for one object key.

    Example:
        ``object_url("assets/static/logo.png")`` returns
        ``/api/files/assets/static/logo.png``.
    """
    object_key = key if isinstance(key, ObjectKey) else ObjectKey(key)
    return f"/api/files/{quote(object_key.value, safe='/')}"


def public_object_key(value: str) -> ObjectKey:
    """Require one key to belong to a namespace intentionally served over HTTP.

    Example:
        ``public_object_key("assets/static/logo.png")`` succeeds, while
        ``public_object_key("zett.db")`` raises :class:`InvalidObjectKey`.
    """
    key = ObjectKey(value)
    if not any(key.value.startswith(prefix) for prefix in PUBLIC_OBJECT_PREFIXES):
        raise InvalidObjectKey(f"Object key is not publicly served: {value!r}")
    return key


def content_digest(content: bytes) -> tuple[int, str]:
    """Return the size and SHA-256 digest persisted for one object."""
    return len(content), hashlib.sha256(content).hexdigest()

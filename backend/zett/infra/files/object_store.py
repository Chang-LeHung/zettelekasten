"""Local filesystem adapter for the application ObjectStore contract."""

import os
import tempfile
from pathlib import Path, PurePosixPath

from ...application.object_store import (
    ObjectKey,
    ObjectStore,
    StoredObject,
    content_digest,
    object_url,
)
from ...config import settings


class LocalObjectStore(ObjectStore):
    """Store objects below one project root such as ``~/.zettelekasten``.

    Example:
        ``LocalObjectStore(Path.home() / ".zettelekasten")`` writes
        ``assets/static/logo.png`` under that root and serves it through
        ``/api/files/assets/static/logo.png``.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._configured_root = root

    @property
    def root(self) -> Path:
        """Resolve the current root each time so tests and settings can isolate it."""
        root = self._configured_root or settings.storage_root
        return root.expanduser().resolve()

    def resolve(self, key: str | ObjectKey) -> Path:
        """Map a key below root and reject every symlink or path escape."""
        object_key = key if isinstance(key, ObjectKey) else ObjectKey(key)
        root = self.root
        candidate = (root / PurePosixPath(object_key.value)).resolve(strict=False)
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"Object key escapes storage_root: {object_key}")
        return candidate

    def url(self, key: str | ObjectKey) -> str:
        return object_url(key)

    async def write(self, key: str | ObjectKey, content: bytes) -> StoredObject:
        path = self.resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            # The temporary file must live in the destination directory. On a
            # normal filesystem this keeps source and destination on the same
            # filesystem, which is required for os.replace to be an atomic
            # rename instead of a copy followed by a delete.
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
                stream.write(content)
                temporary_path = Path(stream.name)

            # Closing the context manager flushes buffered Python bytes before
            # the rename. os.replace then switches the public key atomically:
            # readers see either the old complete object or the new complete
            # object, never a partially written file at the public key.
            os.replace(temporary_path, path)
        finally:
            # Normal exceptions must not leave hidden temporary files behind.
            # A hard process/host crash can still leave one because finally does
            # not run, so temporary names are intentionally hidden and isolated.
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        size_bytes, sha256 = content_digest(content)
        object_key = key if isinstance(key, ObjectKey) else ObjectKey(key)
        return StoredObject(key=object_key, size_bytes=size_bytes, sha256=sha256)

    async def read(self, key: str | ObjectKey) -> bytes:
        path = self.resolve(key)
        if not path.is_file():
            raise FileNotFoundError(str(key))
        return path.read_bytes()

    async def delete(self, key: str | ObjectKey) -> bool:
        path = self.resolve(key)
        if not path.is_file():
            return False
        path.unlink()
        self._remove_empty_parents(path.parent)
        return True

    async def delete_tree(self, key: str | ObjectKey) -> int:
        """Delete every file below one directory key, then the directory itself."""
        directory = self.resolve(key)
        if not directory.is_dir():
            return 0
        removed = 0
        # Unlink files before their directories so no half-deleted tree can
        # survive a failure partway through the walk.
        for candidate in sorted(directory.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink()
                removed += 1
            elif candidate.is_dir():
                candidate.rmdir()
        directory.rmdir()
        self._remove_empty_parents(directory.parent)
        return removed

    async def exists(self, key: str | ObjectKey) -> bool:
        return self.resolve(key).is_file()

    def ensure_directory(self, key: str | ObjectKey) -> Path:
        path = self.resolve(key)
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise ValueError(f"Object key is not a directory: {key}")
        return path

    def _remove_empty_parents(self, directory: Path) -> None:
        """Remove empty object directories up to, but never including, the root."""
        root = self.root
        current = directory
        while current != root and root in current.parents:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent


_object_store: ObjectStore = LocalObjectStore()


def get_object_store() -> ObjectStore:
    """Return the process-wide object store used by all persistence adapters."""
    return _object_store

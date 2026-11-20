"""Filesystem adapter for saved LaTeX PDF snapshots and source freshness checks."""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from zett._compat import UTC
from zett.infra.log import get_logger

logger = get_logger(__name__)

#: How much of a PDF's end is searched for the ``%%EOF`` marker.
TAIL_BYTES = 1024
#: Upper bound on files inspected by a freshness check, so a read stays cheap.
MAX_SCANNED_FILES = 5000
SOURCE_SUFFIXES = frozenset({".tex", ".bib", ".sty", ".cls", ".bst"})


def _is_complete_pdf(path: Path) -> bool:
    """Return whether a file starts like a PDF and ends with an ``%%EOF`` marker."""
    try:
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return False
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - TAIL_BYTES))
            return b"%%EOF" in stream.read()
    except OSError:
        return False


def copy_atomically(source: Path, destination: Path) -> bool:
    """Copy a PDF next to its destination, validate the copy, then replace in one step.

    The temporary copy is checked, not the source, so a file that grows while it
    is copied cannot slip through. An unusable copy is deleted, the previous
    snapshot stays, and ``False`` is returned.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".snapshot-", suffix=".tmp")
    os.close(descriptor)
    try:
        shutil.copyfile(source, temporary)
        if not _is_complete_pdf(Path(temporary)):
            logger.warning("Kept the previous PDF snapshot; %s is not a complete PDF", source)
            return False
        os.replace(temporary, destination)
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def modified_at(path: Path) -> datetime | None:
    """Return a file's modification time in UTC, or None when it is absent."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def has_newer_source(project: Path, than: float) -> bool:
    """Return whether any LaTeX source outside hidden directories changed after ``than``.

    Hitting the scan cap answers True: unknown is reported as possibly stale.
    """
    scanned = 0
    for directory, names, files in os.walk(project):
        names[:] = [name for name in names if not name.startswith(".")]
        for file in files:
            scanned += 1
            if scanned > MAX_SCANNED_FILES:
                # Too many files to know: warn rather than claim the PDF is current.
                return True
            if Path(file).suffix.lower() not in SOURCE_SUFFIXES:
                continue
            try:
                if (Path(directory) / file).stat().st_mtime > than:
                    return True
            except OSError:
                continue
    return False


def sidecar_path(snapshot: Path) -> Path:
    """Return the file beside a snapshot PDF that names the git commit it was saved at."""
    return snapshot.with_suffix(".json")


def write_commit(snapshot: Path, commit: str | None, saved_at: datetime | None = None) -> None:
    """Record the saved commit (or null) and save time beside the snapshot, atomically."""
    destination = sidecar_path(snapshot)
    destination.parent.mkdir(parents=True, exist_ok=True)
    moment = saved_at or datetime.now(UTC)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".snapshot-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"commit": commit, "saved_at": moment.astimezone(UTC).isoformat()}, stream)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_sidecar(snapshot: Path) -> dict[str, object]:
    try:
        value = json.loads(sidecar_path(snapshot).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_commit(snapshot: Path) -> str | None:
    """Return the recorded saved commit, or None when absent or unreadable."""
    value = _read_sidecar(snapshot).get("commit")
    return value if isinstance(value, str) and value else None


def read_saved_at(snapshot: Path) -> datetime | None:
    """Return the recorded save time (UTC), or None when absent or unreadable."""
    value = _read_sidecar(snapshot).get("saved_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def remove_commit(snapshot: Path) -> None:
    """Delete the saved-commit record."""
    sidecar_path(snapshot).unlink(missing_ok=True)

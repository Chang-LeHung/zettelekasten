"""Filesystem adapter for saved LaTeX PDF snapshots and source freshness checks."""

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SOURCE_SUFFIXES = frozenset({".tex", ".bib", ".sty", ".cls", ".bst"})


def copy_atomically(source: Path, destination: Path) -> None:
    """Copy one file next to its destination, then replace it in one step."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".snapshot-", suffix=".tmp")
    os.close(descriptor)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def modified_at(path: Path) -> datetime | None:
    """Return a file's modification time in UTC, or None when it is absent."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def has_newer_source(project: Path, than: float) -> bool:
    """Return whether any LaTeX source outside hidden directories changed after ``than``."""
    for directory, names, files in os.walk(project):
        names[:] = [name for name in names if not name.startswith(".")]
        for file in files:
            if Path(file).suffix.lower() not in SOURCE_SUFFIXES:
                continue
            try:
                if (Path(directory) / file).stat().st_mtime > than:
                    return True
            except OSError:
                continue
    return False

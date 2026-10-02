"""Refuse to publish a distribution whose pinned dependencies are not on PyPI.

``zettelekasten`` pins ``agim`` and ``zett-weixin`` exactly, so publishing it
before them would leave a wheel nobody can install. The check reads the built
distribution — the same metadata PyPI will serve — and asks PyPI whether each
pinned internal dependency exists.

    python3 .github/scripts/check_release_pins.py dist/zettelekasten/*.whl
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

#: Dependencies published from this repository, which is the order they must
#: appear on PyPI in.
INTERNAL = ("agim", "zett-weixin")


def metadata_of(path: Path) -> str:
    """Return the METADATA text of one wheel, or of one sdist."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            name = next(name for name in archive.namelist() if name.endswith("METADATA"))
            return archive.read(name).decode("utf-8")
    import tarfile

    with tarfile.open(path) as archive:
        member = next(item for item in archive.getmembers() if item.name.endswith("PKG-INFO"))
        return archive.extractfile(member).read().decode("utf-8")


def pins(text: str) -> dict[str, str]:
    """Return the exact internal pins a distribution declares."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        requirement = line.split(":", 1)[1].strip()
        name, _, version = requirement.partition("==")
        name = name.strip()
        if name in INTERNAL and version:
            found[name] = version.split(";")[0].strip()
    return found


def published(name: str, version: str) -> bool:
    """Whether one exact version of a project is already on PyPI."""
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def main(paths: list[str]) -> int:
    if not paths:
        raise SystemExit("usage: check_release_pins.py <distribution> [<distribution> ...]")
    for raw in paths:
        path = Path(raw)
        text = metadata_of(path)
        missing = sorted(f"{name}=={version}" for name, version in pins(text).items() if not published(name, version))
        if missing:
            print(f"{path.name} needs {', '.join(missing)} on PyPI first", file=sys.stderr)
            return 1
        print(f"{path.name}: every pinned internal dependency is on PyPI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

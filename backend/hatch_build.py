"""Publish the repository README as this package's long description.

Hatchling requires a readme path inside the project directory, and this project
lives in ``backend/`` while the product README lives at the repository root. The
hook reads that file at build time, so the PyPI page and the README can never
drift apart.
"""

from pathlib import Path

from hatchling.metadata.plugin.interface import MetadataHookInterface


class RootReadmeMetadataHook(MetadataHookInterface):
    """Inline the repository README into the package metadata."""

    def update(self, metadata: dict) -> None:
        readme = Path(self.root).parent / "README.md"
        metadata["readme"] = {
            "content-type": "text/markdown",
            "text": readme.read_text(encoding="utf-8"),
        }

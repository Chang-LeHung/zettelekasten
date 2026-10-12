"""Talk to PyPI, and to the installer that owns this running copy."""

from .installer import Installer, InstallOutcome, detect_installer, run_installer
from .pypi import PROJECT_NAME, PypiClient, PypiError

__all__ = [
    "Installer",
    "InstallOutcome",
    "PROJECT_NAME",
    "PypiClient",
    "PypiError",
    "detect_installer",
    "run_installer",
]

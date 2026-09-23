"""Zett session, asset, and artifact storage foundation."""

import sys
from pathlib import Path

# Source checkouts keep agim as a sibling project rather than a
# subpackage. Installed deployments resolve it through the normal dependency.
_AGIM_SOURCE = Path(__file__).resolve().parent.parent / "agim" / "src"
if _AGIM_SOURCE.is_dir() and str(_AGIM_SOURCE) not in sys.path:
    sys.path.insert(0, str(_AGIM_SOURCE))

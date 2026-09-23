"""Zett session, asset, and artifact storage foundation."""

import sys
from pathlib import Path

# Source checkouts keep these packages as siblings rather than subpackages, and
# a running dev server can reload while `uv sync` is rewriting the editable
# installs. Resolving the sibling sources here keeps imports working through
# that window. Installed deployments resolve them through normal dependencies.
_SIBLING_PACKAGES = ("agim", "zett-weixin")
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
for _name in _SIBLING_PACKAGES:
    _source = _BACKEND_ROOT / _name / "src"
    if _source.is_dir() and str(_source) not in sys.path:
        sys.path.insert(0, str(_source))

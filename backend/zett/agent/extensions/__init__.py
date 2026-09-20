"""Zett's adapters to the zett-agent extension point.

One extension per Zett domain: it implements ``AgentExtension`` and registers
the tools and hooks the runtime calls while a turn runs. Container-level
capabilities such as slash commands and ``@`` references live in
``zett.agent.plugins`` instead.
"""

from .artifacts import ArtifactExtension
from .assets import AssetDetails, AssetExtension, AssetInput
from .context_composition import CONTEXT_COMPOSITION_EVENT, ContextCompositionExtension, context_composition
from .tags import TagExtension

__all__ = [
    "ArtifactExtension",
    "AssetDetails",
    "AssetExtension",
    "AssetInput",
    "CONTEXT_COMPOSITION_EVENT",
    "ContextCompositionExtension",
    "TagExtension",
    "context_composition",
]

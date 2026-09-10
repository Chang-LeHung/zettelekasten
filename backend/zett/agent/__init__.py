"""Minimal zett-agent composition and SSE transport."""

from .assets import AssetDetails, AssetExtension, AssetInput
from .dispatcher import SSESend, ZettelkastenEventDispatcher, encode_sse, event_payload
from .runtime import close_zettelkasten_agent, get_zettelkasten_agent, initialize_zettelkasten_agent
from .zettelkasten import ZettelkastenAgent

__all__ = [
    "SSESend",
    "AssetDetails",
    "AssetExtension",
    "AssetInput",
    "ZettelkastenAgent",
    "ZettelkastenEventDispatcher",
    "encode_sse",
    "event_payload",
    "initialize_zettelkasten_agent",
    "get_zettelkasten_agent",
    "close_zettelkasten_agent",
]

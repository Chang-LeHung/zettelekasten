"""Minimal zett-agent composition and SSE transport."""

from .assets import AssetDetails, AssetExtension, AssetInput
from .config import ZettelkastenAgentConfig
from .context_composition import CONTEXT_COMPOSITION_EVENT, ContextCompositionExtension, context_composition
from .dispatcher import SSESend, ZettelkastenEventDispatcher, encode_sse, event_payload
from .slash import (
    SlashCommandDefinition,
    SlashCommandHandler,
    SlashCommandInvocation,
    ZettelkastenContainer,
    ZettelkastenExt,
)
from .slash_skills import SkillSlashCommandExtension
from .zettelkasten import ZettelkastenAgent

__all__ = [
    "SSESend",
    "AssetDetails",
    "AssetExtension",
    "AssetInput",
    "ZettelkastenAgent",
    "ZettelkastenAgentConfig",
    "CONTEXT_COMPOSITION_EVENT",
    "ContextCompositionExtension",
    "SkillSlashCommandExtension",
    "SlashCommandDefinition",
    "SlashCommandHandler",
    "SlashCommandInvocation",
    "ZettelkastenEventDispatcher",
    "ZettelkastenContainer",
    "ZettelkastenExt",
    "encode_sse",
    "event_payload",
    "context_composition",
]

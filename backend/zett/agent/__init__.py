"""Minimal zett-agent composition and SSE transport."""

from .at_command import (
    AtCommandDefinition,
    AtCommandHandler,
    AtCommandInvocation,
    AtCommandItem,
    AtCommandSource,
    at_command_message,
    stable_at_command_id,
)
from .config import ZettelkastenAgentConfig
from .container import ZettelkastenContainer, ZettelkastenExt
from .dispatcher import SSESend, ZettelkastenEventDispatcher, encode_sse, event_payload
from .extensions import (
    CONTEXT_COMPOSITION_EVENT,
    ArtifactExtension,
    AssetDetails,
    AssetExtension,
    AssetInput,
    ContextCompositionExtension,
    context_composition,
)
from .plugins import (
    SessionArtifactAtCommandSource,
    SessionAssetAtCommandSource,
    SessionReferenceExtension,
    SkillSlashCommandExtension,
)
from .slash import (
    SlashCommandDefinition,
    SlashCommandHandler,
    SlashCommandInvocation,
)
from .zettelkasten import ZettelkastenAgent

__all__ = [
    "SSESend",
    "AssetDetails",
    "AssetExtension",
    "AssetInput",
    "AtCommandDefinition",
    "AtCommandHandler",
    "AtCommandItem",
    "AtCommandInvocation",
    "AtCommandSource",
    "ArtifactExtension",
    "ZettelkastenAgent",
    "ZettelkastenAgentConfig",
    "CONTEXT_COMPOSITION_EVENT",
    "ContextCompositionExtension",
    "SkillSlashCommandExtension",
    "SessionArtifactAtCommandSource",
    "SessionAssetAtCommandSource",
    "SessionReferenceExtension",
    "SlashCommandDefinition",
    "SlashCommandHandler",
    "SlashCommandInvocation",
    "ZettelkastenEventDispatcher",
    "ZettelkastenContainer",
    "ZettelkastenExt",
    "encode_sse",
    "event_payload",
    "at_command_message",
    "context_composition",
    "stable_at_command_id",
]

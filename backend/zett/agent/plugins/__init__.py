"""Zett's own container plugins.

Each plugin implements ``ZettelkastenExt`` and registers container capabilities
that the browser can invoke: the slash commands of ``slash_skills`` and the
``@`` reference kinds of ``at_sources``. Extensions that plug into the
zett-agent runtime instead live in ``zett.agent.extensions``.
"""

from .at_sources import (
    SESSION_AT_COMMAND_LIMIT,
    SessionArtifactAtCommandSource,
    SessionAssetAtCommandSource,
    SessionReferenceExtension,
)
from .slash_skills import SkillSlashCommandExtension

__all__ = [
    "SESSION_AT_COMMAND_LIMIT",
    "SessionArtifactAtCommandSource",
    "SessionAssetAtCommandSource",
    "SessionReferenceExtension",
    "SkillSlashCommandExtension",
]

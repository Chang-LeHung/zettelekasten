"""``@`` reference sources for the assets and artifacts of one session.

The conversation already owns both resource families, so the container exposes
them as two ``@`` sources instead of teaching the browser about asset and
artifact metadata. Listing returns only what the reference menu renders; the
turn carries kinds and IDs, and the ``get_asset`` and ``get_artifact`` tools stay
responsible for reading content.
"""

from collections.abc import AsyncIterator, Sequence

from zett_agent import AgentEvent

from ...infra.dao import artifact_storage, session_asset_storage
from ...models import ArtifactListOptions, SessionAssetListOptions
from ...schemas import AgentArtifact, SessionAssetOut, SessionAssetType
from ..at_command import (
    AtCommandHandler,
    AtCommandInvocation,
    AtCommandItem,
    AtCommandSource,
    at_command_message,
)
from ..container import ZettelkastenContainer, ZettelkastenExt

#: One conversation lists at most this many referenceable resources per kind.
SESSION_AT_COMMAND_LIMIT = 200


def _human_size(size_bytes: int) -> str:
    """Format one stored payload size for the reference menu."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


class SessionAssetAtCommandSource(AtCommandSource):
    """Reference one asset of the current conversation with ``@name``."""

    owner = "assets"
    kind = "asset"

    async def items(self, session_id: str) -> Sequence[AtCommandItem]:
        """List every asset owned by the conversation."""
        assets = await session_asset_storage.list(
            SessionAssetListOptions(session_id=session_id, limit=SESSION_AT_COMMAND_LIMIT)
        )
        return [self._item(asset) for asset in assets]

    async def verify(self, session_id: str, item: AtCommandItem) -> bool:
        """Confirm one referenced asset still belongs to the conversation."""
        return await session_asset_storage.get_for_session(session_id, item.target_id) is not None

    def _item(self, asset: SessionAssetOut) -> AtCommandItem:
        return self.item(
            target_id=asset.id,
            label=asset.name,
            description=self._description(asset),
        )

    @staticmethod
    def _description(asset: SessionAssetOut) -> str:
        label = f"{asset.asset_type.value} asset"
        if asset.asset_type is SessionAssetType.LINK and asset.source_url:
            return f"{label} · {asset.source_url}"
        if asset.size_bytes:
            return f"{label} · {_human_size(asset.size_bytes)}"
        return label


class SessionArtifactAtCommandSource(AtCommandSource):
    """Reference one artifact of the current conversation with ``@name``."""

    owner = "artifacts"
    kind = "artifact"

    async def items(self, session_id: str) -> Sequence[AtCommandItem]:
        """List every artifact produced inside the conversation."""
        artifacts = await artifact_storage.list(
            ArtifactListOptions(session_id=session_id, limit=SESSION_AT_COMMAND_LIMIT)
        )
        return [self._item(artifact) for artifact in artifacts]

    async def verify(self, session_id: str, item: AtCommandItem) -> bool:
        """Confirm one referenced artifact still belongs to the conversation."""
        return await artifact_storage.get_for_session(session_id, item.target_id) is not None

    def _item(self, artifact: AgentArtifact) -> AtCommandItem:
        content = artifact.editable_content
        title = str(getattr(content, "title", "") or artifact.artifact_type.value)
        return self.item(
            target_id=artifact.id,
            label=title,
            description=f"{artifact.artifact_type.value} · {artifact.status.value}",
        )


class SessionReferenceExtension(ZettelkastenExt):
    """Register the session asset and artifact ``@`` commands on one container."""

    name = "session-references"

    async def register(self, container: ZettelkastenContainer) -> None:
        """Expose current-conversation resources to the ``@`` menu."""
        sources: tuple[AtCommandSource, ...] = (
            SessionAssetAtCommandSource(),
            SessionArtifactAtCommandSource(),
        )
        for source in sources:
            container.register_at_command(
                owner=source.owner,
                kind=source.kind,
                source=source,
                handler=_reference_handler(),
            )


def _reference_handler() -> AtCommandHandler:
    """Build the handler that names one referenced resource for the Agent.

    The content stays behind ``get_asset`` and ``get_artifact``: the turn only
    learns the kind and ID of what the user pointed at, and the Raw Log records
    the browser message so the conversation UI can show what the user typed.
    """

    async def handler(invocation: AtCommandInvocation) -> AsyncIterator[AgentEvent]:
        message = at_command_message(invocation.message, (invocation.item,))
        async for event in invocation.prompt(message=message):
            yield event

    return handler


__all__ = [
    "SESSION_AT_COMMAND_LIMIT",
    "SessionArtifactAtCommandSource",
    "SessionAssetAtCommandSource",
    "SessionReferenceExtension",
]

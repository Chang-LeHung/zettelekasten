"""Session-scoped asset tools for the Zettelkasten Agent."""

import base64
import binascii
import json
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from zett_agent import AgentExtension, AgentRunContext, SystemMessage, tool

from ..infra.dao import session_asset_storage
from ..models import SessionAssetListOptions
from ..schemas import SessionAssetCreate, SessionAssetOut, SessionAssetType


class AssetInput(BaseModel):
    """Complete model-authored replacement payload for one session asset."""

    model_config = ConfigDict(extra="forbid")

    asset_type: SessionAssetType = Field(description="Asset category: text, link, image, or file")
    name: str = Field(min_length=1, max_length=500, description="User-facing asset name")
    mime_type: str | None = Field(default=None, max_length=255, description="IANA media type when known")
    text_content: str | None = Field(default=None, description="Complete content for a text asset")
    source_url: str | None = Field(default=None, description="Complete external URL for a link asset")
    content_base64: str | None = Field(default=None, description="Base64 payload for an image or file asset")
    metadata: dict[str, object] = Field(default_factory=dict, description="Application-specific JSON metadata")

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        """Require exactly the content representation used by the selected type."""
        supplied = {
            "text": self.text_content is not None,
            "link": self.source_url is not None,
            "binary": self.content_base64 is not None,
        }
        match self.asset_type:
            case SessionAssetType.TEXT:
                valid = supplied == {"text": True, "link": False, "binary": False}
            case SessionAssetType.LINK:
                valid = supplied == {"text": False, "link": True, "binary": False}
            case SessionAssetType.IMAGE | SessionAssetType.FILE:
                valid = supplied == {"text": False, "link": False, "binary": True}
        if not valid:
            raise ValueError(f"Asset content does not match type {self.asset_type.value!r}")
        return self


class AssetDetails(SessionAssetOut):
    """Asset metadata with optional binary content requested explicitly by the model."""

    content_base64: str | None = Field(
        default=None,
        description="Complete Base64 binary payload; omitted unless include_binary_content is true",
    )


def _decode_binary(content_base64: str | None) -> bytes | None:
    """Decode a model-provided Base64 payload while tolerating visual line wrapping."""
    if content_base64 is None:
        return None
    try:
        return base64.b64decode("".join(content_base64.split()), validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Asset content_base64 is not valid Base64") from error


def _write_model(session_id: str, asset: AssetInput) -> SessionAssetCreate:
    """Attach trusted request identity to a validated model-authored asset payload."""
    return SessionAssetCreate(
        session_id=session_id,
        asset_type=asset.asset_type,
        name=asset.name,
        mime_type=asset.mime_type,
        content=_decode_binary(asset.content_base64),
        text_content=asset.text_content,
        source_url=asset.source_url,
        metadata=asset.metadata,
    )


class AssetExtension(AgentExtension):
    """Expose session-isolated asset CRUD tools and current asset context."""

    async def on_tool(self, context: AgentRunContext) -> None:
        """Register asset tools bound to the current session identity."""
        session_id = context.config.session_id

        @tool
        async def create_asset(asset: AssetInput) -> SessionAssetOut:
            """Create a text, link, image, or file asset in this conversation.

            Args:
                asset: Complete typed asset payload; binary content must be Base64 encoded.

            Snippet:
                create_asset(asset={"asset_type": "text", "name": "notes.md", "text_content": "# Notes"})

            Guidelines:
                - Create an asset only when the user requests a durable session attachment.
                - Use text for inline source material and link for an external URL.
            """
            return await session_asset_storage.create(_write_model(session_id, asset))

        @tool
        async def get_asset(asset_id: str, include_binary_content: bool = False) -> AssetDetails:
            """Read one asset owned by this conversation.

            Args:
                asset_id: Stable asset ID from the current conversation.
                include_binary_content: Include Base64 bytes for an image or file when explicitly needed.

            Snippet:
                get_asset(asset_id="...", include_binary_content=False)

            Guidelines:
                - Leave binary content excluded unless the task truly requires the bytes.
                - Never use an asset ID from another conversation.
            """
            asset = await self._asset(session_id, asset_id)
            encoded: str | None = None
            if include_binary_content and asset.asset_type in {SessionAssetType.IMAGE, SessionAssetType.FILE}:
                path = await session_asset_storage.content_path(session_id, asset_id)
                if path is None:
                    raise ValueError(f"Asset content is unavailable: {asset_id}")
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return AssetDetails(**asset.model_dump(), content_base64=encoded)

        @tool
        async def update_asset(asset_id: str, asset: AssetInput) -> SessionAssetOut:
            """Replace all editable fields and content of one conversation asset.

            Args:
                asset_id: Stable asset ID from the current conversation.
                asset: Complete replacement payload, including content and metadata.

            Snippet:
                update_asset(asset_id="...", asset={"asset_type": "link", "name": "Docs", "source_url": "https://example.com"})

            Guidelines:
                - Call get_asset first when existing fields must be retained.
                - Treat this as full replacement rather than a partial patch.
            """
            await self._asset(session_id, asset_id)
            return await session_asset_storage.update(asset_id, _write_model(session_id, asset))

        @tool
        async def delete_asset(asset_id: str) -> bool:
            """Delete one asset owned by this conversation.

            Args:
                asset_id: Stable asset ID from the current conversation.

            Snippet:
                delete_asset(asset_id="...")

            Guidelines:
                - Delete an asset only when the user's intent is explicit.
            """
            await self._asset(session_id, asset_id)
            return await session_asset_storage.delete(asset_id)

        @tool
        async def list_assets(
            query: str | None = None,
            asset_types: tuple[SessionAssetType, ...] = (),
            limit: Annotated[int, Field(ge=1, le=500)] = 100,
            offset: Annotated[int, Field(ge=0)] = 0,
        ) -> list[SessionAssetOut]:
            """List assets owned by this conversation with filtering and pagination.

            Args:
                query: Optional case-insensitive name fragment.
                asset_types: Optional asset categories to include.
                limit: Maximum number of results from 1 through 500.
                offset: Number of matching assets to skip.

            Snippet:
                list_assets(asset_types=["text", "link"], limit=50, offset=0)

            Guidelines:
                - Use filters and pagination instead of guessing asset IDs.
            """
            return await session_asset_storage.list(
                SessionAssetListOptions(
                    session_id=session_id,
                    query=query,
                    asset_types=tuple(item.value for item in asset_types),
                    limit=limit,
                    offset=offset,
                )
            )

        for registered in (create_asset, get_asset, update_asset, delete_asset, list_assets):
            context.register_tool(registered)

    async def on_state(self, context: AgentRunContext) -> None:
        """Expose lightweight asset content without injecting binary payloads."""
        assets = await session_asset_storage.list(
            SessionAssetListOptions(session_id=context.config.session_id, limit=500)
        )
        if not assets:
            return
        payload = [
            {
                "id": asset.id,
                "type": asset.asset_type,
                "name": asset.name,
                "mime_type": asset.mime_type,
                "size_bytes": asset.size_bytes,
                "text_content": asset.text_content,
                "source_url": asset.source_url,
                "metadata": asset.metadata,
            }
            for asset in assets
        ]
        workspace = SystemMessage(content="Current session assets:\n" + json.dumps(payload, ensure_ascii=False))
        instructions = [item for item in context.state.messages if isinstance(item, SystemMessage)]
        dialogue = [item for item in context.state.messages if not isinstance(item, SystemMessage)]
        context.state.messages[:] = [*instructions, workspace, *dialogue]

    @staticmethod
    async def _asset(session_id: str, asset_id: str) -> SessionAssetOut:
        """Resolve an asset only inside the active session boundary."""
        asset = await session_asset_storage.get_for_session(session_id, asset_id)
        if asset is None:
            raise ValueError(f"Asset not found in this session: {asset_id}")
        return asset

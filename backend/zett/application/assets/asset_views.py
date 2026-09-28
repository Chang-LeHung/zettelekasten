"""Bounded, model-facing views of one static asset.

A file in the global library is a stored row: name, media type, size, digest,
object key, metadata, timestamps. Only a little of that is something the next
tool call acts on, so the tools answer with this view instead — the id that
classifying the file needs, what the file is, the URL this site serves it from,
and the collections it currently carries.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...schemas import StaticAssetEntity


class StaticAssetReceipt(BaseModel):
    """What a model needs after publishing or classifying a file, and nothing more.

    ``id`` is deliberately here, unlike the session asset upload's answer: this
    id is what ``set_asset_tags`` takes, so omitting it would only make the model
    guess. ``tags`` is the complete set that tool replaces.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable static asset id for later tool calls")
    name: str = Field(description="Stored file name")
    mime_type: str | None = Field(default=None, description="Detected media type when known")
    content_url: str = Field(description="Site URL that serves this file")
    tags: list[str] = Field(description="Collection paths this file carries; the set set_asset_tags replaces")


def static_asset_receipt(asset: StaticAssetEntity) -> StaticAssetReceipt:
    """Project one stored static asset into the bounded answer a tool returns."""
    return StaticAssetReceipt(
        id=asset.id,
        name=asset.name,
        mime_type=asset.mime_type,
        content_url=asset.content_url,
        tags=[tag.path for tag in asset.tags],
    )

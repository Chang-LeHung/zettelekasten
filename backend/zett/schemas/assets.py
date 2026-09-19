"""Write and read models for session and global assets."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SessionAssetType(StrEnum):
    """Supported asset categories within a persisted agent session."""

    TEXT = "text"
    IMAGE = "image"
    LINK = "link"
    FILE = "file"


class SessionAssetCreate(BaseModel):
    """Complete write model consumed by the session asset storage adapter."""

    session_id: str = Field(description="Owning session UUID")
    asset_type: SessionAssetType = Field(description="Asset storage and rendering category")
    name: str = Field(min_length=1, max_length=500, description="User-facing asset name")
    mime_type: str | None = Field(default=None, max_length=255, description="IANA media type when known")
    content: bytes | None = Field(default=None, exclude=True, repr=False, description="Binary file payload")
    text_content: str | None = Field(default=None, description="Inline text asset content")
    source_url: str | None = Field(default=None, description="External URL represented by a link asset")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class SessionAssetOut(BaseModel):
    """Serialized session asset with a controlled content endpoint."""

    id: str = Field(description="Stable asset UUID")
    session_id: str = Field(description="Owning session UUID")
    asset_type: SessionAssetType = Field(description="Asset storage and rendering category")
    name: str = Field(description="User-facing asset name")
    mime_type: str | None = Field(default=None, description="IANA media type when known")
    size_bytes: int = Field(default=0, description="Stored payload size in bytes")
    sha256: str | None = Field(default=None, description="SHA-256 digest of stored content")
    text_content: str | None = Field(default=None, description="Inline text content for text assets")
    source_url: str | None = Field(default=None, description="External URL for link assets")
    content_url: str | None = Field(default=None, description="Application URL for reading stored content")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


class StaticAssetCreate(BaseModel):
    """Complete write model for one session-independent uploaded file."""

    name: str = Field(min_length=1, max_length=500, description="User-facing filename")
    mime_type: str | None = Field(default=None, max_length=255, description="IANA media type when known")
    content: bytes = Field(exclude=True, repr=False, description="Binary file payload")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class StaticAssetOut(BaseModel):
    """Serialized file that is available across conversations."""

    id: str = Field(description="Stable static asset UUID")
    name: str = Field(description="User-facing filename")
    mime_type: str | None = Field(default=None, description="IANA media type when known")
    size_bytes: int = Field(default=0, description="Stored payload size in bytes")
    sha256: str = Field(description="SHA-256 digest of stored content")
    content_url: str = Field(description="Application URL for reading or downloading the file")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")

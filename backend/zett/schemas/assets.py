"""Write and read models for session and global assets."""

from datetime import datetime

from pydantic import BaseModel, Field

from .._compat import StrEnum
from .common import HttpUrl, NonBlankName500


class SessionAssetType(StrEnum):
    """Supported asset categories within a persisted agent session."""

    TEXT = "text"
    IMAGE = "image"
    LINK = "link"
    FILE = "file"


class SessionAssetCreate(BaseModel):
    """Complete write model consumed by the session asset storage adapter.

    Content is mutually exclusive by asset type:

    - ``text`` uses ``text_content``.
    - ``link`` uses exactly one of ``source_url`` or ``source_path``.
    - ``image`` / ``file`` use ``content`` for owned bytes. A reference-only
      image/file may use ``source_path`` instead, but then no bytes are copied.
    """

    session_id: str = Field(description="Owning session UUID")
    asset_type: SessionAssetType = Field(description="Asset storage and rendering category")
    name: NonBlankName500 = Field(description="User-facing asset name")
    mime_type: str | None = Field(default=None, max_length=255, description="IANA media type when known")
    content: bytes | None = Field(default=None, exclude=True, repr=False, description="Binary file payload")
    # Inline text is stored directly in SQLite rather than ObjectStore.
    text_content: str | None = Field(default=None, description="Inline text content for a text asset")
    # External URLs remain external. They are not ObjectStore keys and are never
    # rewritten into /api/files URLs.
    source_url: HttpUrl | None = Field(default=None, description="External URL for an external-link asset")
    # Internal references use one relative ObjectKey. Example:
    # "assets/static/01a0....pdf". The bytes remain owned by the target object.
    source_path: str | None = Field(default=None, description="Relative ObjectKey referenced by this asset")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class SessionAssetEntity(BaseModel):
    """Serialized session asset with a controlled content endpoint.

    The three content representations are intentionally separate:

    - ``text_content``: inline data, no file URL.
    - ``source_url``: external URL, no local file URL.
    - ``storage_path``: this row owns bytes under ObjectStore.
    - ``source_path``: this row references another ObjectStore object.
    - ``content_url``: response-only URL derived from storage_path/source_path.
    """

    id: str = Field(description="Stable asset UUID")
    session_id: str = Field(description="Owning session UUID")
    asset_type: SessionAssetType = Field(description="Asset storage and rendering category")
    name: str = Field(description="User-facing asset name")
    mime_type: str | None = Field(default=None, description="IANA media type when known")
    size_bytes: int = Field(default=0, description="Stored payload size in bytes")
    sha256: str | None = Field(default=None, description="SHA-256 digest of stored content")
    # Inline payload; null for image/file/link/reference assets.
    text_content: str | None = Field(default=None, description="Inline text content for text assets")
    # External URL only; null for local assets and internal ObjectStore references.
    source_url: str | None = Field(default=None, description="External URL for link assets")
    # Relative key for bytes owned by this SessionAsset. Example:
    # "assets/sessions/<session_id>/<asset_id>.png". Never absolute.
    storage_path: str | None = Field(default=None, description="Relative ObjectKey owned by this asset")
    # Relative key for bytes owned by another object, such as an imported
    # StaticAsset. Example: "assets/static/<static_asset_id>.pdf".
    source_path: str | None = Field(default=None, description="Relative ObjectKey referenced by this asset")
    # Response-only convenience URL. It is computed with ObjectStore.url() and
    # is not persisted. Example: "/api/files/assets/static/abc.pdf".
    content_url: str | None = Field(default=None, description="Derived URL for previewing or downloading content")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")


class StaticAssetCreate(BaseModel):
    """Complete write model for one session-independent uploaded file."""

    name: NonBlankName500 = Field(description="User-facing filename")
    mime_type: str | None = Field(default=None, max_length=255, description="IANA media type when known")
    content: bytes = Field(exclude=True, repr=False, description="Binary file payload")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")


class StaticAssetEntity(BaseModel):
    """Serialized file that is available across conversations.

    ``storage_path`` is the persisted identity. ``content_url`` is derived on
    every response so clients do not need to know the file endpoint layout.
    """

    id: str = Field(description="Stable static asset UUID")
    name: str = Field(description="User-facing filename")
    mime_type: str | None = Field(default=None, description="IANA media type when known")
    size_bytes: int = Field(default=0, description="Stored payload size in bytes")
    sha256: str = Field(description="SHA-256 digest of stored content")
    # Example: "assets/static/<static_asset_id>.pdf".
    storage_path: str = Field(description="Relative ObjectKey below the configured storage root")
    # Example: "/api/files/assets/static/<static_asset_id>.pdf".
    content_url: str = Field(description="Derived URL for previewing or downloading this object")
    metadata: dict[str, object] = Field(default_factory=dict, description="Extensible asset metadata")
    created_at: datetime = Field(description="UTC creation timestamp")
    updated_at: datetime = Field(description="UTC last modification timestamp")

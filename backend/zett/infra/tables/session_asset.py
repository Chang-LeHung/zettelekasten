"""Persistence model for assets owned by an agent session."""

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionAssetRow(Base):
    """Metadata for text, link, image, or file assets owned by one session."""

    __tablename__ = "session_assets"

    # Stable UUID7 identity used by APIs, tool calls, and the content endpoint.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Owning Agent session UUID; asset reads and writes are always session-scoped.
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    # Persisted SessionAssetType code: text=1, image=2, link=3, file=4.
    asset_type: Mapped[int] = mapped_column(Integer, index=True)
    # User-facing asset name, also used as the download filename when applicable.
    name: Mapped[str] = mapped_column(String(500), index=True)
    # IANA media type when known, such as image/png or application/pdf.
    mime_type: Mapped[str | None] = mapped_column(String(255))
    # Byte length of the stored payload; text and URLs are measured as UTF-8.
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # SHA-256 digest of the same payload used to calculate size_bytes.
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # Relative ObjectKey for bytes owned by this row.
    # Example: "assets/sessions/<session_id>/<asset_id>.png".
    # Text assets, external links, and object references keep this null.
    storage_path: Mapped[str | None] = mapped_column(String(1_000))
    # Inline content for text assets; null for image, link, file, and reference assets.
    text_content: Mapped[str | None] = mapped_column(Text)
    # External URL for links to resources outside this application. This is not
    # an ObjectKey and is never rewritten into an /api/files URL.
    source_url: Mapped[str | None] = mapped_column(Text)
    # Relative ObjectKey when this row references another stored object without
    # owning its bytes. Example: importing a StaticAsset stores
    # "assets/static/<static_asset_id>.pdf" here.
    source_path: Mapped[str | None] = mapped_column(String(1_000))
    # JSON-encoded extensible metadata stored with the physical column name "metadata".
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    # UTC timestamp when the asset record was created.
    created_at: Mapped[datetime] = mapped_column(index=True)
    # UTC timestamp when editable metadata or stored content was last replaced.
    updated_at: Mapped[datetime] = mapped_column(index=True)

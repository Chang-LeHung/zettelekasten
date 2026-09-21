"""Persistence model for files shared outside Agent sessions."""

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StaticAssetRow(Base):
    """Metadata for one uploaded file stored under the global static asset root."""

    __tablename__ = "static_assets"

    # Stable UUID7 identity used by the list and content endpoints.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Original user-facing filename, also used for downloads.
    name: Mapped[str] = mapped_column(String(500), index=True)
    # IANA media type when provided by the upload request.
    mime_type: Mapped[str | None] = mapped_column(String(255))
    # Byte length of the uploaded payload.
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # SHA-256 digest of the uploaded payload.
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # Relative ObjectKey for bytes owned by this global asset.
    # Example: "assets/static/<static_asset_id>.pdf". Never absolute.
    storage_path: Mapped[str] = mapped_column(String(1_000))
    # JSON-encoded extensible metadata stored with the physical column name "metadata".
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    # UTC timestamp when the asset record was created.
    created_at: Mapped[datetime] = mapped_column(index=True)
    # UTC timestamp when metadata or file content was last replaced.
    updated_at: Mapped[datetime] = mapped_column(index=True)

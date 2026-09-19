"""Persistence model for assets owned by an agent session."""

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionAssetModel(Base):
    """Metadata for text, link, image, or file assets owned by one session."""

    __tablename__ = "session_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_type: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    storage_name: Mapped[str | None] = mapped_column(String(100))
    text_content: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(index=True)
    updated_at: Mapped[datetime] = mapped_column(index=True)

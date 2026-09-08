from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionArtifactModel(Base):
    """Typed, versioned output produced within an agent session."""

    __tablename__ = "session_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    artifact_type: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    content_json: Mapped[str] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(index=True)


class SessionAssetModel(Base):
    """Metadata for text, link, image, or file assets owned by one session."""

    __tablename__ = "session_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_type: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    storage_name: Mapped[str | None] = mapped_column(String(100))
    text_content: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(index=True)
    updated_at: Mapped[datetime] = mapped_column(index=True)


class ProviderModel(Base):
    """Locally configured model endpoint with an encrypted API credential."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    provider: Mapped[int] = mapped_column(Integer, index=True)
    model: Mapped[str] = mapped_column(String(200), index=True)
    base_url: Mapped[str | None] = mapped_column(Text)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(index=True)

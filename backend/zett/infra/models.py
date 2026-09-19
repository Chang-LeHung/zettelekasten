from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionArtifactModel(Base):
    """Typed, versioned output produced within an agent session."""

    __tablename__ = "session_artifacts"
    __table_args__ = (
        Index("ix_artifacts_created", "created_at", "id"),
        Index("ix_artifacts_session_created", "session_id", "created_at", "id"),
    )

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
    __table_args__ = (
        Index("ix_assets_created", "created_at", "id"),
        Index("ix_assets_session_created", "session_id", "created_at", "id"),
    )

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


class KeyValueModel(Base):
    """One mutable, versioned JSON value stored under a unique key."""

    __tablename__ = "key_values"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(index=True)
    updated_at: Mapped[datetime] = mapped_column(index=True)


class TagModel(Base):
    """One stable node in the persistent library classification tree."""

    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    path: Mapped[str] = mapped_column(String(500), index=True)
    normalized_path: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(index=True)
    updated_at: Mapped[datetime] = mapped_column(index=True)


class ArtifactTagModel(Base):
    """Explicit association between an artifact and a confirmed tag."""

    __tablename__ = "artifact_tags"
    __table_args__ = (
        UniqueConstraint("artifact_id", "tag_id", name="uq_artifact_tag"),
        Index("ix_artifact_tags_tag_artifact", "tag_id", "artifact_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(36), index=True)
    tag_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(index=True)


class ModelUsageActivityModel(Base):
    """One completed model request's token usage, retained for activity charts."""

    __tablename__ = "model_usage_activity"
    __table_args__ = (
        Index("ix_model_usage_activity_day", "created_at", "id"),
        Index("ix_model_usage_activity_session_day", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36))
    request_id: Mapped[str | None] = mapped_column(String(36))
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(index=True)

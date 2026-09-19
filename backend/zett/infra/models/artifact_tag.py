"""Persistence model for confirmed artifact-tag assignments."""

from datetime import datetime

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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

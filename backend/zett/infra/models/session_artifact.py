"""Persistence model for versioned artifacts produced within an agent session."""

from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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

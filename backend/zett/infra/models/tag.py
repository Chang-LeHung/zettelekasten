"""Persistence model for the persistent library classification tree."""

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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

"""Persistence model for locally configured model providers."""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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

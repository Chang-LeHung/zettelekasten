"""Persistence models for the persistent library classification tree and its links."""

from datetime import datetime
from enum import IntEnum

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ....schemas import TagTargetType
from .base import Base


class TagTargetTypeCode(IntEnum):
    """Persisted value of ``tag_links.target_type``: which kind of thing a link classifies."""

    ARTIFACT = 1
    ASSET = 2


TARGET_TO_CODE = {
    TagTargetType.ARTIFACT: TagTargetTypeCode.ARTIFACT,
    TagTargetType.ASSET: TagTargetTypeCode.ASSET,
}
CODE_TO_TARGET = {int(code): target for target, code in TARGET_TO_CODE.items()}


class TagRow(Base):
    """One stable node in the persistent library classification tree.

    A tag names a category, never a kind of thing: the same node may classify an
    artifact and a static asset, so the type lives on the link, not here.
    """

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


class TagLinkRow(Base):
    """Explicit association between one tag and one classified resource.

    ``target_type`` says which kind of thing ``target_id`` names — an artifact
    (``TagTargetTypeCode.ARTIFACT``) or a static asset
    (``TagTargetTypeCode.ASSET``) — so one taxonomy classifies both without a
    second relation table, and ``(target_type, target_id)`` is what "the tagged
    resource" means everywhere else: reads group by target, and a delete of the
    resource removes exactly its own rows.

    There are no foreign keys and no cascades by design. Deleting an artifact or
    a static asset removes its rows here explicitly, in the same transaction that
    removes the resource, so a link never outlives what it classifies and no
    cascade rule can remove a row nobody asked it to.
    """

    __tablename__ = "tag_links"
    __table_args__ = (
        # One resource cannot carry the same tag twice.
        UniqueConstraint("target_type", "target_id", "tag_id", name="uq_tag_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # TagTargetTypeCode: artifact=1, static asset=2.
    target_type: Mapped[int] = mapped_column(Integer, index=True)
    # Artifact UUID or static asset UUID, selected by target_type.
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    tag_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(index=True)

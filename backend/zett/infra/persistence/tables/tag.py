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

    A tag belongs to exactly one library. ``target_type`` says which, so the
    artifact library and the static asset library each have their own tree: the
    same path may exist once in each, and a tag created for one kind is never
    visible, selectable, or assignable in the other. A tag names a category
    *within* a library; the library it belongs to is part of its identity, which
    is why uniqueness is per ``(target_type, normalized_path)``.
    """

    __tablename__ = "tags"
    __table_args__ = (
        # One path per library: the same path may exist for artifacts and for
        # static assets, and each is its own collection.
        UniqueConstraint("target_type", "normalized_path", name="uq_tag_target_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # TagTargetTypeCode: artifact=1, static asset=2.
    target_type: Mapped[int] = mapped_column(Integer, index=True)
    path: Mapped[str] = mapped_column(String(500), index=True)
    normalized_path: Mapped[str] = mapped_column(String(500), index=True)
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

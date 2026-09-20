"""Persistence definitions for versioned artifacts produced by agent sessions.

Everything the artifact tables need is defined here: the integer codes stored in
``artifact_type`` and ``status``, the ``session_artifacts`` row itself, and the
explicit ``artifact_tags`` relation. Storage adapters translate between these
rows and the typed schemas; they do not redefine the encoding.
"""

from datetime import datetime
from enum import IntEnum

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...schemas import ArtifactStatus, ArtifactType
from .base import Base


class ArtifactTypeCode(IntEnum):
    """Persisted value of ``session_artifacts.artifact_type``."""

    CARD = 1
    ARTICLE = 2
    IMAGE = 3
    SLIDES = 4
    LATEX_PDF = 5


class ArtifactStatusCode(IntEnum):
    """Persisted value of ``session_artifacts.status``."""

    DRAFT = 1
    SAVED = 2


TYPE_TO_CODE = {
    ArtifactType.CARD: ArtifactTypeCode.CARD,
    ArtifactType.ARTICLE: ArtifactTypeCode.ARTICLE,
    ArtifactType.IMAGE: ArtifactTypeCode.IMAGE,
    ArtifactType.SLIDES: ArtifactTypeCode.SLIDES,
    ArtifactType.LATEX_PDF: ArtifactTypeCode.LATEX_PDF,
}
CODE_TO_TYPE = {int(code): artifact_type for artifact_type, code in TYPE_TO_CODE.items()}
STATUS_TO_CODE = {
    ArtifactStatus.DRAFT: ArtifactStatusCode.DRAFT,
    ArtifactStatus.SAVED: ArtifactStatusCode.SAVED,
}
CODE_TO_STATUS = {int(code): status for status, code in STATUS_TO_CODE.items()}


class SessionArtifactRow(Base):
    """Typed, versioned output produced within an agent session."""

    __tablename__ = "session_artifacts"

    # Stable UUID7 identity used by APIs, tool calls, and the content endpoint.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Owning Agent session UUID; artifact reads and writes are always session-scoped.
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    # ArtifactTypeCode: card=1, article=2, image=3, slides=4, latex_pdf=5.
    artifact_type: Mapped[int] = mapped_column(Integer, index=True)
    # ArtifactStatusCode: draft=1, saved=2. Draft is the pre-publish lifecycle
    # state; it does not describe whether a draft edit is pending.
    status: Mapped[int] = mapped_column(Integer, index=True)
    # Searchable title: the content title, or the PDF name without its extension.
    title: Mapped[str] = mapped_column(String(500), index=True)
    # Published content, written only by a user action (artifact save or editor).
    # An empty string means the artifact has never been published.
    content_json: Mapped[str] = mapped_column(Text)
    # Working copy the model edits: the proposed content, or a copy of the
    # published content right after a save. Null only for rows predating drafts.
    draft_content_json: Mapped[str | None] = mapped_column(Text, default=None)
    # Original user text this artifact was produced from, when the caller had it.
    raw_content: Mapped[str | None] = mapped_column(Text)
    # Monotonic revision counter incremented by every write, draft or published.
    version: Mapped[int] = mapped_column(Integer, default=1)
    # JSON-encoded extensible metadata stored with the physical column name "metadata".
    metadata_value: Mapped[str] = mapped_column("metadata", Text, default="{}")
    # UTC timestamp when the artifact row was created.
    created_at: Mapped[datetime] = mapped_column()
    # UTC timestamp when content, draft, or metadata was last replaced.
    updated_at: Mapped[datetime] = mapped_column(index=True)


class ArtifactTagRow(Base):
    """Explicit association between an artifact and a confirmed tag.

    The relation has no foreign keys by design: deleting an artifact removes its
    rows here explicitly, together with the artifact row itself.
    """

    __tablename__ = "artifact_tags"
    __table_args__ = (
        UniqueConstraint("artifact_id", "tag_id", name="uq_artifact_tag"),
        Index("ix_artifact_tags_tag_artifact", "tag_id", "artifact_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(36), index=True)
    tag_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(index=True)

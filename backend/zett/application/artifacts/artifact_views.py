"""Bounded, model-facing views of one artifact.

An artifact tool used to answer with the stored row: the published content, the
model's draft, the original source text, metadata, timestamps, and the owning
session. Almost none of that is something the next step acts on. A model that
updates a long article sent the text in the same turn, so echoing it back — twice,
once per body — spends the whole context on data that is already there, and
``raw_content`` can be another megabyte of it.

These views keep what a tool result is actually for. A write answers with
identity and state, the confirmed tags a whole-set replacement must include, and
the server-assigned locations a caller is not allowed to guess; the one read that
needs the bodies returns them together, without the stored row's noise.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...schemas import (
    AgentArtifactEntity,
    ArtifactContent,
    ArtifactStatus,
    ArtifactType,
    ImageArtifactContent,
    LatexPdfArtifactContent,
)


class ArtifactReceipt(BaseModel):
    """What a model needs after writing an artifact, and nothing more.

    ``content`` and ``draft_content`` are deliberately absent: the model just
    wrote them, and ``get_artifact`` reads the complete pair when a later edit
    needs exact body text. ``project_path`` is the one server-assigned location
    the LaTeX guidelines require the model to preserve, ``asset_path`` is the
    uploaded key an image artifact points at, and ``tags`` is the complete set
    ``set_artifact_tags`` replaces.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable artifact ID for later tool calls")
    artifact_type: ArtifactType = Field(description="Artifact kind")
    status: ArtifactStatus = Field(description="draft until the user saves it, saved after that")
    version: int = Field(ge=1, description="Monotonic revision number")
    title: str = Field(description="User-facing title the artifact now carries")
    pending_draft: bool = Field(description="The model's draft still differs from the published content")
    tags: list[str] = Field(description="Confirmed tag paths; the complete set set_artifact_tags replaces")
    content_url: str | None = Field(
        default=None, description="File URL when the artifact owns one, such as a PDF or local image"
    )
    project_path: str | None = Field(default=None, description="LaTeX only: server-assigned project directory key")
    pdf_name: str | None = Field(default=None, description="LaTeX only: compiled PDF basename")
    asset_path: str | None = Field(default=None, description="Image only: relative key of the local file it points at")


class ArtifactDocument(BaseModel):
    """One artifact's complete published and draft content, without stored noise."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable artifact ID")
    artifact_type: ArtifactType = Field(description="Artifact kind")
    status: ArtifactStatus = Field(description="draft until the user saves it, saved after that")
    version: int = Field(ge=1, description="Monotonic revision number")
    content: ArtifactContent | None = Field(
        default=None,
        description="What the user published; empty until a user saves",
    )
    draft_content: ArtifactContent | None = Field(
        default=None,
        description="The working copy the model edits, equal to content right after a save",
    )
    pending_draft: bool = Field(description="The model's draft still differs from the published content")
    tags: list[str] = Field(description="Confirmed tag paths; the complete set set_artifact_tags replaces")
    content_url: str | None = Field(
        default=None, description="File URL when the artifact owns one, such as a PDF or local image"
    )


def artifact_receipt(artifact: AgentArtifactEntity) -> ArtifactReceipt:
    """Project one written artifact into the bounded answer a write tool returns."""
    content = artifact.editable_content
    latex = content if isinstance(content, LatexPdfArtifactContent) else None
    image = content if isinstance(content, ImageArtifactContent) else None
    return ArtifactReceipt(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        status=artifact.status,
        version=artifact.version,
        title=content.title if content is not None else artifact.artifact_type.value,
        pending_draft=pending_draft(artifact),
        tags=[tag.path for tag in artifact.tags],
        content_url=artifact.content_url,
        project_path=latex.project_path if latex is not None else None,
        pdf_name=latex.pdf_name if latex is not None else None,
        asset_path=image.asset_path if image is not None else None,
    )


def artifact_document(artifact: AgentArtifactEntity) -> ArtifactDocument:
    """Project one artifact into the complete read, without its stored-row fields."""
    return ArtifactDocument(
        id=artifact.id,
        artifact_type=artifact.artifact_type,
        status=artifact.status,
        version=artifact.version,
        content=artifact.content,
        draft_content=artifact.draft_content,
        pending_draft=pending_draft(artifact),
        tags=[tag.path for tag in artifact.tags],
        content_url=artifact.content_url,
    )


def pending_draft(artifact: AgentArtifactEntity) -> bool:
    """Report whether the draft still differs from what the user published."""
    return artifact.draft_content is not None and artifact.draft_content != artifact.content

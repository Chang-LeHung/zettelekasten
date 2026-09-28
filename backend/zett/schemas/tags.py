"""Write and read models for persistent library tags."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .._compat import StrEnum


class TagTargetType(StrEnum):
    """Which kind of resource a tag link classifies.

    The taxonomy itself is shared, so the type belongs to the link: the same tag
    may classify an artifact and a static asset, and a caller that reads or
    replaces one resource's tags states which kind it means.
    """

    ARTIFACT = "artifact"
    ASSET = "asset"


class SuggestedTag(BaseModel):
    """AI-proposed tag that requires user confirmation before saving."""

    path: str = Field(description="Hierarchical tag path")
    existing: bool = Field(description="Whether the path already exists")
    confidence: float = Field(default=0, ge=0, le=1, description="Model confidence from 0 to 1")
    reason: str | None = Field(default=None, description="Short reason for the recommendation")


class TagWrite(BaseModel):
    """Complete mutable fields for one persistent library tag."""

    target_type: TagTargetType = Field(description="Library this tag classifies: artifact or asset")
    path: str = Field(min_length=1, max_length=500, description="Display path separated by slashes")
    normalized_path: str = Field(min_length=1, max_length=500, description="Canonical path used for uniqueness")
    name: str = Field(min_length=1, max_length=100, description="Final display segment")
    parent_id: str | None = Field(default=None, description="Immediate parent tag UUID")
    description: str | None = Field(default=None, max_length=1_000)
    color: str | None = Field(default=None, max_length=32)


class TagEntity(TagWrite):
    """Persistent tag returned by storage and application boundaries."""

    id: str
    created_at: datetime
    updated_at: datetime


class TagRefEntity(BaseModel):
    """Stable tag reference carried by one classified resource."""

    id: str
    path: str
    name: str


class TagTreeEntity(TagEntity):
    """One library's collection tree, with direct and descendant assignment counts.

    A tree is always built for one ``target_type``, so every count describes that
    library alone: the artifact tree never counts a file, and the asset tree
    never counts an artifact.
    """

    direct_count: int = Field(default=0, ge=0)
    total_count: int = Field(default=0, ge=0)
    children: list[TagTreeEntity] = Field(default_factory=list)

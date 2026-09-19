"""Write and read models for persistent library tags."""

from datetime import datetime

from pydantic import BaseModel, Field


class SuggestedTag(BaseModel):
    """AI-proposed tag that requires user confirmation before saving."""

    path: str = Field(description="Hierarchical tag path")
    existing: bool = Field(description="Whether the path already exists")
    confidence: float = Field(default=0, ge=0, le=1, description="Model confidence from 0 to 1")
    reason: str | None = Field(default=None, description="Short reason for the recommendation")


class TagWrite(BaseModel):
    """Complete mutable fields for one persistent library tag."""

    path: str = Field(min_length=1, max_length=500, description="Display path separated by slashes")
    normalized_path: str = Field(min_length=1, max_length=500, description="Canonical path used for uniqueness")
    name: str = Field(min_length=1, max_length=100, description="Final display segment")
    parent_id: str | None = Field(default=None, description="Immediate parent tag UUID")
    description: str | None = Field(default=None, max_length=1_000)
    color: str | None = Field(default=None, max_length=32)


class TagOut(TagWrite):
    """Persistent tag returned by storage and application boundaries."""

    id: str
    created_at: datetime
    updated_at: datetime


class ArtifactTagOut(BaseModel):
    """Stable tag reference assigned to an artifact."""

    id: str
    path: str
    name: str


class TagTreeOut(TagOut):
    """Hierarchical tag facet with direct and descendant artifact counts."""

    direct_count: int = Field(default=0, ge=0)
    total_count: int = Field(default=0, ge=0)
    children: list[TagTreeOut] = Field(default_factory=list)

"""Query options for the storage foundation."""

from pydantic import BaseModel, ConfigDict, Field

from .sessions import SessionType
from .tags import TagTargetType


class SessionListOptions(BaseModel):
    """Pagination for sessions owned by zett-agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    limit: int = Field(default=100, ge=1, le=500, description="Maximum sessions returned")
    offset: int = Field(default=0, ge=0, description="Number of sessions skipped")
    session_types: tuple[SessionType, ...] = Field(default=(), description="Session origins included")


class ArtifactListOptions(BaseModel):
    """Query options for typed artifacts produced by agent sessions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str | None = Field(default=None, description="Owning session UUID")
    artifact_types: tuple[str, ...] = Field(default=(), description="Artifact kinds included in the result")
    statuses: tuple[str, ...] = Field(default=(), description="Lifecycle states included in the result")
    tag_ids: tuple[str, ...] = Field(default=(), description="Assigned tag UUIDs included in the result")
    query: str | None = Field(default=None, description="Text matched against artifact titles")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum artifacts returned")
    offset: int = Field(default=0, ge=0, description="Number of artifacts skipped")


class TagListOptions(BaseModel):
    """Filtering and pagination for persistent library tags."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: TagTargetType | None = Field(default=None, description="Library whose tree to list")
    prefix: str | None = Field(default=None, description="Normalized hierarchical path prefix")
    limit: int = Field(default=500, ge=1, le=2_000, description="Maximum tags returned")
    offset: int = Field(default=0, ge=0, description="Number of tags skipped")


class SessionAssetListOptions(BaseModel):
    """Query options for assets attached to a Zettelkasten Agent session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str | None = Field(default=None, description="Owning session UUID")
    query: str | None = Field(default=None, description="Text matched against asset names")
    asset_types: tuple[str, ...] = Field(default=(), description="Asset types included in the result")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum assets returned")
    offset: int = Field(default=0, ge=0, description="Number of assets skipped")


class StaticAssetListOptions(BaseModel):
    """Filtering and pagination for files stored outside any session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str | None = Field(default=None, description="Text matched against asset names")
    tag_ids: tuple[str, ...] = Field(default=(), description="Tag ids that must classify the asset")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum assets returned")
    offset: int = Field(default=0, ge=0, description="Number of assets skipped")


class ProviderListOptions(BaseModel):
    """Filtering and pagination for locally configured model providers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str | None = Field(default=None, description="Text matched against provider names and model IDs")
    providers: tuple[str, ...] = Field(default=(), description="Provider protocols included in the result")
    enabled: bool | None = Field(default=None, description="Filter by enabled state")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum providers returned")
    offset: int = Field(default=0, ge=0, description="Number of providers skipped")

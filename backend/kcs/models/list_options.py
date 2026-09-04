from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class CardSortField(StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    TITLE = "title"


class TagSortField(StrEnum):
    NAME = "name"
    CREATED_AT = "created_at"
    CARD_COUNT = "card_count"


class CardListOptions(BaseModel):
    """Shared card query model used by HTTP and persistence adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    query: str | None = Field(default=None, alias="q", description="Text matched against searchable card fields")
    card_type: str | None = Field(default=None, alias="type", description="Shorthand for one included card type")
    tag_id: int | None = Field(default=None, description="Shorthand for one included tag ID")
    card_types: tuple[str, ...] = Field(default=(), description="Card types that may appear in the result")
    statuses: tuple[str, ...] = Field(default=(), description="Lifecycle statuses that may appear in the result")
    include_tag_ids: tuple[int, ...] = Field(default=(), description="Tag IDs cards must include")
    exclude_tag_ids: tuple[int, ...] = Field(default=(), description="Tag IDs cards must not include")
    match_all_tags: bool = Field(default=False, description="Require every included tag instead of any included tag")
    include_descendants: bool = Field(default=True, description="Include descendants of selected tags")
    source: str | None = Field(default=None, description="Source text to match")
    created_from: str | None = Field(default=None, description="Inclusive lower creation timestamp")
    created_to: str | None = Field(default=None, description="Inclusive upper creation timestamp")
    updated_from: str | None = Field(default=None, description="Inclusive lower update timestamp")
    updated_to: str | None = Field(default=None, description="Inclusive upper update timestamp")
    has_summary: bool | None = Field(default=None, description="Filter by whether a summary exists")
    sort_by: CardSortField = Field(default=CardSortField.UPDATED_AT, description="Field used to order results")
    sort_direction: SortDirection = Field(default=SortDirection.DESC, description="Result ordering direction")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum number of cards returned")
    offset: int = Field(default=0, ge=0, description="Number of matching cards skipped")

    @property
    def resolved_card_types(self) -> tuple[str, ...]:
        """Combine the singular type shorthand with the multi-value filter."""
        values = (*self.card_types, *((self.card_type,) if self.card_type else ()))
        return tuple(dict.fromkeys(values))

    @property
    def resolved_include_tag_ids(self) -> tuple[int, ...]:
        """Combine the singular tag shorthand with the multi-value filter."""
        values = (*self.include_tag_ids, *((self.tag_id,) if self.tag_id is not None else ()))
        return tuple(dict.fromkeys(values))


class ArticleListOptions(BaseModel):
    """Query options for permanent Markdown articles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str | None = Field(default=None, description="Text matched against article fields")
    statuses: tuple[str, ...] = Field(default=(), description="Lifecycle statuses included in the result")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum number of articles returned")
    offset: int = Field(default=0, ge=0, description="Number of matching articles skipped")


class LibraryListOptions(BaseModel):
    """Query options for the unified card and article library."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    query: str | None = Field(default=None, alias="q", description="Text matched across library resources")
    tag_id: int | None = Field(default=None, description="Restrict cards to one tag and its descendants")
    item_types: tuple[str, ...] = Field(default=(), description="Resource kinds included in the result")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum number of resources returned")
    offset: int = Field(default=0, ge=0, description="Number of matching resources skipped")


class TagListOptions(BaseModel):
    """Shared tag query model used by application and persistence adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str | None = Field(default=None, description="Text matched against tag names and paths")
    parent_id: int | None = Field(default=None, description="Return direct children of this tag")
    ancestor_id: int | None = Field(default=None, description="Return the subtree rooted at this tag")
    include_descendants: bool = Field(default=False, description="Include every descendant of the selected ancestor")
    tree: bool = Field(default=True, description="Return nested tags instead of a flat sequence")
    sort_by: TagSortField = Field(default=TagSortField.NAME, description="Field used to order tags")
    sort_direction: SortDirection = Field(default=SortDirection.ASC, description="Tag ordering direction")
    limit: int = Field(default=500, ge=1, le=1000, description="Maximum number of tags returned")
    offset: int = Field(default=0, ge=0, description="Number of matching tags skipped")


class AgentSessionListOptions(BaseModel):
    """Query options for persisted KCS Agent sessions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str | None = Field(default=None, description="Optional lifecycle status filter")
    query: str | None = Field(default=None, description="Text matched against session titles")
    limit: int = Field(default=50, ge=1, le=200, description="Maximum sessions returned")
    offset: int = Field(default=0, ge=0, description="Number of sessions skipped")


class RawLogMessageListOptions(BaseModel):
    """Query options for the immutable message log."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(description="Owning session UUID")
    after_sequence: int = Field(default=0, ge=0, description="Exclusive lower sequence boundary")
    through_sequence: int | None = Field(default=None, ge=1, description="Inclusive upper sequence boundary")
    limit: int = Field(default=10000, ge=1, le=10000, description="Maximum log entries returned")


class ContextSnapshotListOptions(BaseModel):
    """Query options for versioned context snapshots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(description="Owning session UUID")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum snapshots returned")


class ArtifactListOptions(BaseModel):
    """Query options for typed artifacts produced by agent sessions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str | None = Field(default=None, description="Owning session UUID")
    artifact_types: tuple[str, ...] = Field(default=(), description="Artifact kinds included in the result")
    statuses: tuple[str, ...] = Field(default=(), description="Lifecycle states included in the result")
    query: str | None = Field(default=None, description="Text matched against artifact titles")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum artifacts returned")
    offset: int = Field(default=0, ge=0, description="Number of artifacts skipped")


class SessionAssetListOptions(BaseModel):
    """Query options for assets attached to a KCS Agent session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str | None = Field(default=None, description="Owning session UUID")
    query: str | None = Field(default=None, description="Text matched against asset names")
    asset_types: tuple[str, ...] = Field(default=(), description="Asset types included in the result")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum assets returned")
    offset: int = Field(default=0, ge=0, description="Number of assets skipped")


class AIProviderListOptions(BaseModel):
    """Query options for locally configured AI providers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str | None = Field(default=None, description="Text matched against provider names and model IDs")
    provider: str | None = Field(default=None, description="Provider protocol identifier to include")
    enabled: bool | None = Field(default=None, description="Filter by whether a provider can be selected")
    limit: int = Field(default=100, ge=1, le=500, description="Maximum providers returned")
    offset: int = Field(default=0, ge=0, description="Number of matching providers skipped")

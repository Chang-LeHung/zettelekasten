from datetime import datetime

from sqlalchemy import Boolean, Column, Float, Integer, String, Table, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


card_tags_table = Table(
    "card_tags",
    Base.metadata,
    Column("card_id", String(36), primary_key=True),
    Column("tag_id", Integer, primary_key=True),
)


class TagModel(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column()


class CardModel(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), default="note")
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()


class ArticleModel(Base):
    """Permanent long-form Markdown resource stored independently from its source session."""

    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    subtitle: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)
    tag_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(index=True)


class AISettingsModel(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str | None] = mapped_column(Text)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(default=0.2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column()


class AIProviderModel(Base):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str | None] = mapped_column(Text)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(default=0.2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()


class AgentSessionModel(Base):
    """Persisted conversation aggregate; enum values are stored as integers."""

    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[int] = mapped_column(Integer, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()
    last_activity_at: Mapped[datetime] = mapped_column(index=True)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[float | None] = mapped_column(Float)
    total_time_to_first_token_ms: Mapped[float] = mapped_column(Float, default=0)
    timed_run_count: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens_per_second: Mapped[float] = mapped_column(Float, default=0)
    throughput_run_count: Mapped[int] = mapped_column(Integer, default=0)


class AgentRunModel(Base):
    """One observable Zett Agent turn with GenAI usage and latency metrics."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    turn_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[int] = mapped_column(Integer, index=True)
    provider_id: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    reasoning_effort: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(index=True)
    first_token_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()
    total_duration_ms: Mapped[float | None] = mapped_column(Float)
    time_to_first_token_ms: Mapped[float | None] = mapped_column(Float)
    generation_duration_ms: Mapped[float | None] = mapped_column(Float)
    reasoning_duration_ms: Mapped[float | None] = mapped_column(Float)
    tool_duration_ms: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_rate: Mapped[float | None] = mapped_column(Float)
    output_tokens_per_second: Mapped[float | None] = mapped_column(Float)
    input_cost: Mapped[float | None] = mapped_column(Float)
    output_cost: Mapped[float | None] = mapped_column(Float)
    total_cost: Mapped[float | None] = mapped_column(Float)
    model_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    finish_reason: Mapped[str | None] = mapped_column(String(100))
    error_type: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AgentToolCallModel(Base):
    """One tool span associated with an agent run."""

    __tablename__ = "agent_tool_calls"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[int] = mapped_column(Integer, index=True)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()


class SessionArtifactModel(Base):
    """Typed, versioned output produced within an agent session."""

    __tablename__ = "session_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    artifact_type: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    content_json: Mapped[str] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)
    linked_resource_id: Mapped[str | None] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(index=True)


class SessionAssetModel(Base):
    """Metadata for text, link, image, or file assets owned by one session."""

    __tablename__ = "session_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_type: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    storage_name: Mapped[str | None] = mapped_column(String(100))
    text_content: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(index=True)
    updated_at: Mapped[datetime] = mapped_column(index=True)

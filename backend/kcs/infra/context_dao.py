import json
from datetime import UTC, datetime
from enum import IntEnum
from typing import cast
from uuid import uuid4

from sqlalchemy import func, select

from ..models import ContextSnapshotListOptions, RawLogMessageListOptions
from ..schemas import (
    AgentMessageOut,
    AgentMessageRole,
    ContextSnapshotCreate,
    ContextSnapshotOut,
    RawLogMessageCreate,
)
from .database import session_scope
from .models import AgentSessionModel, ContextSnapshotModel, RawLogMessageModel


class MessageRoleCode(IntEnum):
    """Numeric persistence representation for raw-log participant roles."""

    SYSTEM = 1
    USER = 2
    ASSISTANT = 3
    TOOL = 4


ROLE_TO_CODE = {
    AgentMessageRole.SYSTEM: MessageRoleCode.SYSTEM,
    AgentMessageRole.USER: MessageRoleCode.USER,
    AgentMessageRole.ASSISTANT: MessageRoleCode.ASSISTANT,
    AgentMessageRole.TOOL: MessageRoleCode.TOOL,
}
CODE_TO_ROLE = {int(code): role for role, code in ROLE_TO_CODE.items()}


def _json_load[JSONValueT](value: str | None, fallback: JSONValueT) -> JSONValueT:
    """Decode one JSON column without leaking untyped ORM values."""
    try:
        return cast(JSONValueT, json.loads(value)) if value else fallback
    except json.JSONDecodeError:
        return fallback


def _message_out(model: RawLogMessageModel) -> AgentMessageOut:
    """Hydrate an immutable raw-log row into the public message model."""
    metadata = _json_load(model.metadata_json, {})
    reasoning_content = metadata.get("reasoning_content")
    return AgentMessageOut(
        id=model.id,
        session_id=model.session_id,
        turn_id=model.turn_id,
        sequence=model.sequence,
        role=CODE_TO_ROLE[model.role],
        content=model.content,
        reasoning_content=reasoning_content if isinstance(reasoning_content, str) else None,
        model=model.model,
        provider=model.provider,
        tool_name=model.tool_name,
        metadata=metadata,
        created_at=model.created_at,
    )


def _snapshot_out(model: ContextSnapshotModel) -> ContextSnapshotOut:
    """Hydrate a snapshot row, including its structured state JSON."""
    return ContextSnapshotOut(
        id=model.id,
        session_id=model.session_id,
        version=model.version,
        base_sequence=model.base_sequence,
        summary=model.summary,
        state=_json_load(model.state_json, {}),
        source_message_count=model.source_message_count,
        source_token_count=model.source_token_count,
        summary_token_count=model.summary_token_count,
        provider=model.provider,
        model=model.model,
        created_at=model.created_at,
    )


class RawLogMessageStorage:
    """Append-only SQLAlchemy storage for authoritative conversation events."""

    def append(self, entity: RawLogMessageCreate) -> AgentMessageOut:
        """Append one event and assign the next session-local sequence."""
        now = datetime.now(UTC)
        with session_scope() as session:
            owner = session.get(AgentSessionModel, entity.session_id)
            if owner is None:
                raise KeyError(f"Agent session not found: {entity.session_id}")
            sequence = (
                session.scalar(
                    select(func.max(RawLogMessageModel.sequence)).where(
                        RawLogMessageModel.session_id == entity.session_id
                    )
                )
                or 0
            ) + 1
            model = RawLogMessageModel(
                id=str(uuid4()),
                session_id=entity.session_id,
                turn_id=entity.turn_id,
                sequence=sequence,
                role=int(ROLE_TO_CODE[entity.role]),
                content=entity.content,
                model=entity.model,
                provider=entity.provider,
                tool_name=entity.tool_name,
                metadata_json=json.dumps(entity.metadata, ensure_ascii=False),
                created_at=now,
            )
            session.add(model)
            owner.message_count += 1
            owner.updated_at = owner.last_activity_at = now
            session.flush()
            return _message_out(model)

    def get(self, message_id: str) -> AgentMessageOut | None:
        """Return one raw event by its stable ID."""
        with session_scope() as session:
            model = session.get(RawLogMessageModel, message_id)
            return _message_out(model) if model else None

    def list(self, options: RawLogMessageListOptions) -> list[AgentMessageOut]:
        """Replay a bounded, ordered segment of one session log."""
        with session_scope() as session:
            statement = select(RawLogMessageModel).where(
                RawLogMessageModel.session_id == options.session_id,
                RawLogMessageModel.sequence > options.after_sequence,
            )
            if options.through_sequence is not None:
                statement = statement.where(RawLogMessageModel.sequence <= options.through_sequence)
            statement = statement.order_by(RawLogMessageModel.sequence).limit(options.limit)
            return [_message_out(model) for model in session.scalars(statement)]


class ContextSnapshotStorage:
    """SQLAlchemy storage for immutable, versioned context snapshots."""

    def create(self, entity: ContextSnapshotCreate) -> ContextSnapshotOut:
        """Append a snapshot whose boundary only moves forward."""
        with session_scope() as session:
            if session.get(AgentSessionModel, entity.session_id) is None:
                raise KeyError(f"Agent session not found: {entity.session_id}")
            latest = session.scalar(
                select(ContextSnapshotModel)
                .where(ContextSnapshotModel.session_id == entity.session_id)
                .order_by(ContextSnapshotModel.version.desc())
                .limit(1)
            )
            if latest is not None and entity.base_sequence <= latest.base_sequence:
                raise ValueError("Snapshot base sequence must move forward")
            model = ContextSnapshotModel(
                id=str(uuid4()),
                session_id=entity.session_id,
                version=(latest.version + 1) if latest else 1,
                base_sequence=entity.base_sequence,
                summary=entity.summary,
                state_json=entity.state.model_dump_json(),
                source_message_count=entity.source_message_count,
                source_token_count=entity.source_token_count,
                summary_token_count=entity.summary_token_count,
                provider=entity.provider,
                model=entity.model,
                created_at=datetime.now(UTC),
            )
            session.add(model)
            session.flush()
            return _snapshot_out(model)

    def latest(self, session_id: str) -> ContextSnapshotOut | None:
        """Return the highest-version snapshot for context reconstruction."""
        with session_scope() as session:
            model = session.scalar(
                select(ContextSnapshotModel)
                .where(ContextSnapshotModel.session_id == session_id)
                .order_by(ContextSnapshotModel.version.desc())
                .limit(1)
            )
            return _snapshot_out(model) if model else None

    def list(self, options: ContextSnapshotListOptions) -> list[ContextSnapshotOut]:
        """List snapshot history newest first for audit and debugging."""
        with session_scope() as session:
            models = session.scalars(
                select(ContextSnapshotModel)
                .where(ContextSnapshotModel.session_id == options.session_id)
                .order_by(ContextSnapshotModel.version.desc())
                .limit(options.limit)
            )
            return [_snapshot_out(model) for model in models]


raw_log_message_storage = RawLogMessageStorage()
context_snapshot_storage = ContextSnapshotStorage()

import json
from datetime import UTC, datetime
from enum import IntEnum
from typing import cast
from uuid import uuid4

from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from ..models import AgentSessionListOptions, ArtifactListOptions
from ..schemas import (
    AgentMessageOut,
    AgentMessageRole,
    AgentRunOut,
    AgentRunStatus,
    AgentSessionCreate,
    AgentSessionOut,
    AgentSessionStatus,
    AgentToolCallOut,
    ReasoningEffort,
)
from .database import session_scope
from .models import (
    AgentRunModel,
    AgentSessionModel,
    AgentToolCallModel,
    ContextSnapshotModel,
    RawLogMessageModel,
    SessionAssetModel,
)
from .storage import Storage


class SessionStatusCode(IntEnum):
    ACTIVE = 1
    COMPLETED = 2
    FAILED = 3
    ARCHIVED = 4


class RunStatusCode(IntEnum):
    RUNNING = 1
    SUCCEEDED = 2
    FAILED = 3
    CANCELLED = 4


SESSION_TO_CODE = {
    AgentSessionStatus.ACTIVE: SessionStatusCode.ACTIVE,
    AgentSessionStatus.COMPLETED: SessionStatusCode.COMPLETED,
    AgentSessionStatus.FAILED: SessionStatusCode.FAILED,
    AgentSessionStatus.ARCHIVED: SessionStatusCode.ARCHIVED,
}
CODE_TO_SESSION = {int(code): status for status, code in SESSION_TO_CODE.items()}
RUN_TO_CODE = {
    AgentRunStatus.RUNNING: RunStatusCode.RUNNING,
    AgentRunStatus.SUCCEEDED: RunStatusCode.SUCCEEDED,
    AgentRunStatus.FAILED: RunStatusCode.FAILED,
    AgentRunStatus.CANCELLED: RunStatusCode.CANCELLED,
}
CODE_TO_RUN = {int(code): status for status, code in RUN_TO_CODE.items()}


def _json_load[JSONValueT](value: str | None, fallback: JSONValueT) -> JSONValueT:
    """Decode persisted JSON while preserving the caller's fallback type."""
    try:
        return cast(JSONValueT, json.loads(value)) if value else fallback
    except json.JSONDecodeError:
        return fallback


def _tool_call_out(model: AgentToolCallModel) -> AgentToolCallOut:
    return AgentToolCallOut(
        id=model.id,
        run_id=model.run_id,
        session_id=model.session_id,
        tool_name=model.tool_name,
        status=CODE_TO_RUN[model.status],
        input=_json_load(model.input_json, {}),
        output=_json_load(model.output_json, None),
        duration_ms=model.duration_ms,
        error_message=model.error_message,
        started_at=model.started_at,
        ended_at=model.ended_at,
    )


def _run_out(model: AgentRunModel, tool_calls: list[AgentToolCallOut] | None = None) -> AgentRunOut:
    metadata = _json_load(model.metadata_json, {})
    return AgentRunOut(
        id=model.id,
        trace_id=model.trace_id,
        span_id=model.span_id,
        session_id=model.session_id,
        turn_id=model.turn_id,
        agent_name=model.agent_name,
        status=CODE_TO_RUN[model.status],
        provider_id=model.provider_id,
        provider=model.provider,
        model=model.model,
        reasoning_effort=(
            ReasoningEffort.OFF if model.reasoning_effort == "disabled" else ReasoningEffort(model.reasoning_effort)
        ),
        started_at=model.started_at,
        first_token_at=model.first_token_at,
        ended_at=model.ended_at,
        total_duration_ms=model.total_duration_ms,
        time_to_first_token_ms=model.time_to_first_token_ms,
        generation_duration_ms=model.generation_duration_ms,
        reasoning_duration_ms=model.reasoning_duration_ms,
        tool_duration_ms=model.tool_duration_ms,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        reasoning_tokens=model.reasoning_tokens,
        cache_read_tokens=model.cache_read_tokens,
        cache_creation_tokens=model.cache_creation_tokens,
        total_tokens=model.total_tokens,
        cache_hit_rate=model.cache_hit_rate,
        output_tokens_per_second=model.output_tokens_per_second,
        input_cost=model.input_cost,
        output_cost=model.output_cost,
        total_cost=model.total_cost,
        model_call_count=model.model_call_count,
        tool_call_count=model.tool_call_count,
        retry_count=model.retry_count,
        finish_reason=model.finish_reason,
        error_type=model.error_type,
        error_message=model.error_message,
        metadata=metadata,
        tool_calls=tool_calls or [],
    )


class AgentSessionStorage(Storage[AgentSessionCreate, AgentSessionOut, str, AgentSessionListOptions]):
    """SQLAlchemy storage for the KCS Agent session aggregate and observability records."""

    def create(self, entity: AgentSessionCreate) -> AgentSessionOut:
        now = datetime.now(UTC)
        with session_scope() as session:
            model = AgentSessionModel(
                id=str(uuid4()),
                agent_name="KCS Agent",
                title=entity.title,
                status=int(SessionStatusCode.ACTIVE),
                metadata_json=json.dumps(entity.metadata, ensure_ascii=False),
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
            session.add(model)
            session.flush()
            return self._session_out(session, model, include_details=True)

    def get(self, entity_id: str) -> AgentSessionOut | None:
        with session_scope() as session:
            model = session.get(AgentSessionModel, entity_id)
            return self._session_out(session, model, include_details=True) if model else None

    def exists(self, entity_id: str) -> bool:
        """Check session existence without hydrating messages, runs, or artifacts."""
        with session_scope() as session:
            return session.scalar(select(AgentSessionModel.id).where(AgentSessionModel.id == entity_id)) is not None

    def update(self, entity_id: str, entity: AgentSessionCreate) -> AgentSessionOut:
        with session_scope() as session:
            model = session.get(AgentSessionModel, entity_id)
            if model is None:
                raise KeyError(f"Agent session not found: {entity_id}")
            model.title = entity.title
            model.metadata_json = json.dumps(entity.metadata, ensure_ascii=False)
            model.updated_at = datetime.now(UTC)
            session.flush()
            return self._session_out(session, model, include_details=True)

    def delete(self, entity_id: str) -> bool:
        with session_scope() as session:
            model = session.get(AgentSessionModel, entity_id)
            if model is None:
                return False
            for child in (
                RawLogMessageModel,
                ContextSnapshotModel,
                AgentRunModel,
                AgentToolCallModel,
                SessionAssetModel,
            ):
                session.execute(sql_delete(child).where(child.session_id == entity_id))
            session.delete(model)
            return True

    def list(self, options: AgentSessionListOptions | None = None) -> list[AgentSessionOut]:
        options = options or AgentSessionListOptions()
        with session_scope() as session:
            statement = select(AgentSessionModel)
            if options.status:
                status = AgentSessionStatus(options.status)
                statement = statement.where(AgentSessionModel.status == int(SESSION_TO_CODE[status]))
            if options.query:
                statement = statement.where(AgentSessionModel.title.ilike(f"%{options.query}%"))
            statement = (
                statement.order_by(AgentSessionModel.created_at.desc(), AgentSessionModel.id.desc())
                .limit(options.limit)
                .offset(options.offset)
            )
            return [self._session_out(session, model, include_details=False) for model in session.scalars(statement)]

    def append_message(
        self,
        session_id: str,
        turn_id: str,
        role: AgentMessageRole,
        content: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        tool_name: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AgentMessageOut:
        """Append a role-bearing message and assign the next session sequence number."""
        from ..schemas import RawLogMessageCreate
        from .context_dao import raw_log_message_storage

        return raw_log_message_storage.append(
            RawLogMessageCreate(
                session_id=session_id,
                turn_id=turn_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
                tool_name=tool_name,
                metadata=metadata or {},
            )
        )

    def start_run(
        self,
        session_id: str,
        turn_id: str,
        provider_id: int | None,
        provider: str | None,
        model: str | None,
        reasoning_effort: ReasoningEffort,
    ) -> AgentRunOut:
        """Create the root observable run for one conversation turn."""
        now = datetime.now(UTC)
        with session_scope() as session:
            owner = self._require_session(session, session_id)
            owner.status = int(SessionStatusCode.ACTIVE)
            run = AgentRunModel(
                id=str(uuid4()),
                trace_id=uuid4().hex,
                span_id=uuid4().hex[:16],
                session_id=session_id,
                turn_id=turn_id,
                agent_name="KCS Agent",
                status=int(RunStatusCode.RUNNING),
                provider_id=provider_id,
                provider=provider,
                model=model,
                reasoning_effort=reasoning_effort.value,
                started_at=now,
            )
            session.add(run)
            owner.turn_count += 1
            owner.updated_at = owner.last_activity_at = now
            session.flush()
            return _run_out(run)

    def finish_run(self, run_id: str, status: AgentRunStatus, metrics: dict[str, object]) -> AgentRunOut:
        """Finalize a run, persist measurements, and update session aggregates."""
        with session_scope() as session:
            run = session.get(AgentRunModel, run_id)
            if run is None:
                raise KeyError(f"Agent run not found: {run_id}")
            for name, value in metrics.items():
                if hasattr(run, name):
                    setattr(run, name, value)
            run.status = int(RUN_TO_CODE[status])
            owner = self._require_session(session, run.session_id)
            owner.updated_at = owner.last_activity_at = run.ended_at or datetime.now(UTC)
            owner.total_input_tokens += run.input_tokens
            owner.total_output_tokens += run.output_tokens
            owner.total_reasoning_tokens += run.reasoning_tokens
            owner.total_cache_read_tokens += run.cache_read_tokens
            owner.total_tokens += run.total_tokens
            if run.total_cost is not None:
                owner.total_cost = (owner.total_cost or 0) + run.total_cost
            if run.time_to_first_token_ms is not None:
                owner.total_time_to_first_token_ms += run.time_to_first_token_ms
                owner.timed_run_count += 1
            if run.output_tokens_per_second is not None:
                owner.total_output_tokens_per_second += run.output_tokens_per_second
                owner.throughput_run_count += 1
            if status == AgentRunStatus.FAILED:
                owner.status = int(SessionStatusCode.FAILED)
            session.flush()
            calls = self._tool_calls(session, run.id)
            return _run_out(run, calls)

    def record_tool_call(
        self,
        run_id: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, object],
        output: object | None,
        status: AgentRunStatus,
        started_at: datetime,
        ended_at: datetime,
        duration_ms: float,
        error_message: str | None = None,
    ) -> AgentToolCallOut:
        """Persist one tool span with validated input, output, timing, and failure state."""
        with session_scope() as session:
            model = AgentToolCallModel(
                id=tool_call_id or str(uuid4()),
                run_id=run_id,
                session_id=session_id,
                tool_name=tool_name,
                status=int(RUN_TO_CODE[status]),
                input_json=json.dumps(arguments, ensure_ascii=False),
                output_json=json.dumps(output, ensure_ascii=False, default=str) if output is not None else None,
                duration_ms=duration_ms,
                error_message=error_message,
                started_at=started_at,
                ended_at=ended_at,
            )
            session.add(model)
            session.flush()
            return _tool_call_out(model)

    def _session_out(self, session, model: AgentSessionModel, include_details: bool) -> AgentSessionOut:
        messages = []
        runs = []
        artifacts = []
        if include_details:
            from ..models import RawLogMessageListOptions
            from .context_dao import raw_log_message_storage

            messages = raw_log_message_storage.list(RawLogMessageListOptions(session_id=model.id))
            run_models = session.scalars(
                select(AgentRunModel).where(AgentRunModel.session_id == model.id).order_by(AgentRunModel.started_at)
            ).all()
            runs = [_run_out(item, self._tool_calls(session, item.id)) for item in run_models]
            from .artifact_dao import artifact_storage

            artifacts = list(artifact_storage.list(ArtifactListOptions(session_id=model.id)))
        return AgentSessionOut(
            id=model.id,
            agent_name=model.agent_name,
            title=model.title,
            status=CODE_TO_SESSION[model.status],
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_activity_at=model.last_activity_at,
            message_count=model.message_count,
            turn_count=model.turn_count,
            total_input_tokens=model.total_input_tokens,
            total_output_tokens=model.total_output_tokens,
            total_reasoning_tokens=model.total_reasoning_tokens,
            total_cache_read_tokens=model.total_cache_read_tokens,
            total_tokens=model.total_tokens,
            total_cost=model.total_cost,
            average_time_to_first_token_ms=model.total_time_to_first_token_ms / model.timed_run_count
            if model.timed_run_count
            else None,
            average_output_tokens_per_second=model.total_output_tokens_per_second / model.throughput_run_count
            if model.throughput_run_count
            else None,
            cache_hit_rate=model.total_cache_read_tokens / model.total_input_tokens
            if model.total_input_tokens
            else None,
            metadata=_json_load(model.metadata_json, {}),
            messages=messages,
            runs=runs,
            artifacts=artifacts,
        )

    @staticmethod
    def _require_session(session, session_id: str) -> AgentSessionModel:
        model = session.get(AgentSessionModel, session_id)
        if model is None:
            raise KeyError(f"Agent session not found: {session_id}")
        return model

    @staticmethod
    def _tool_calls(session, run_id: str) -> list[AgentToolCallOut]:
        models = session.scalars(
            select(AgentToolCallModel)
            .where(AgentToolCallModel.run_id == run_id)
            .order_by(AgentToolCallModel.started_at)
        ).all()
        return [_tool_call_out(model) for model in models]


agent_session_storage = AgentSessionStorage()

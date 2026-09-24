"""SQLite persistence for per-request model token activity."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from zett_agent import ModelUsageActivityDay, ModelUsageActivityRecord, new_uuid7

from ...._compat import UTC
from ....schemas import ModelUsageActivitySeries, UsageActivityDayRecord
from ..database import session_scope
from ..tables import ModelUsageActivityRow


class SQLiteModelUsageActivityStorage:
    """Store raw request counters and aggregate them by UTC calendar day."""

    async def record(self, record: ModelUsageActivityRecord) -> None:
        """Insert one completed model request."""
        async with session_scope() as session:
            session.add(
                ModelUsageActivityRow(
                    id=new_uuid7(),
                    session_id=record.session_id,
                    request_id=record.request_id,
                    provider=record.provider,
                    model=record.model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cache_read_tokens=record.cache_read_tokens,
                    cache_write_tokens=record.cache_write_tokens,
                    reasoning_tokens=record.reasoning_tokens,
                    created_at=record.occurred_at.astimezone(UTC),
                )
            )

    async def activity(self, *, start: date, end: date) -> list[ModelUsageActivityDay]:
        """Return grouped counters for the inclusive UTC date range."""
        if end < start:
            raise ValueError("activity end date cannot precede start date")
        start_at = datetime.combine(start, time.min, tzinfo=UTC)
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
        day = func.date(ModelUsageActivityRow.created_at)
        async with session_scope() as session:
            rows = await session.execute(
                select(
                    day.label("day"),
                    func.count(ModelUsageActivityRow.id).label("requests"),
                    func.sum(ModelUsageActivityRow.input_tokens).label("input_tokens"),
                    func.sum(ModelUsageActivityRow.output_tokens).label("output_tokens"),
                    func.sum(ModelUsageActivityRow.cache_read_tokens).label("cache_read_tokens"),
                    func.sum(ModelUsageActivityRow.cache_write_tokens).label("cache_write_tokens"),
                    func.sum(ModelUsageActivityRow.reasoning_tokens).label("reasoning_tokens"),
                )
                .where(
                    ModelUsageActivityRow.created_at >= start_at,
                    ModelUsageActivityRow.created_at < end_at,
                )
                .group_by(day)
                .order_by(day)
            )
            return [
                ModelUsageActivityDay(
                    date=date.fromisoformat(row.day),
                    requests=int(row.requests or 0),
                    input_tokens=int(row.input_tokens or 0),
                    output_tokens=int(row.output_tokens or 0),
                    cache_read_tokens=int(row.cache_read_tokens or 0),
                    cache_write_tokens=int(row.cache_write_tokens or 0),
                    reasoning_tokens=int(row.reasoning_tokens or 0),
                )
                for row in rows
            ]

    async def model_activity(self, *, start: date, end: date) -> list[ModelUsageActivitySeries]:
        """Return daily counters grouped by provider and model."""
        if end < start:
            raise ValueError("activity end date cannot precede start date")
        start_at = datetime.combine(start, time.min, tzinfo=UTC)
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
        day = func.date(ModelUsageActivityRow.created_at)
        async with session_scope() as session:
            rows = await session.execute(
                select(
                    ModelUsageActivityRow.provider,
                    ModelUsageActivityRow.model,
                    day.label("day"),
                    func.count(ModelUsageActivityRow.id).label("requests"),
                    func.sum(ModelUsageActivityRow.input_tokens).label("input_tokens"),
                    func.sum(ModelUsageActivityRow.output_tokens).label("output_tokens"),
                    func.sum(ModelUsageActivityRow.cache_read_tokens).label("cache_read_tokens"),
                    func.sum(ModelUsageActivityRow.cache_write_tokens).label("cache_write_tokens"),
                    func.sum(ModelUsageActivityRow.reasoning_tokens).label("reasoning_tokens"),
                )
                .where(
                    ModelUsageActivityRow.created_at >= start_at,
                    ModelUsageActivityRow.created_at < end_at,
                )
                .group_by(ModelUsageActivityRow.provider, ModelUsageActivityRow.model, day)
                .order_by(ModelUsageActivityRow.provider, ModelUsageActivityRow.model, day)
            )

        grouped: dict[tuple[str | None, str | None], list[UsageActivityDayRecord]] = {}
        for row in rows:
            key = (row.provider, row.model)
            grouped.setdefault(key, []).append(
                UsageActivityDayRecord(
                    date=date.fromisoformat(row.day),
                    requests=int(row.requests or 0),
                    input_tokens=int(row.input_tokens or 0),
                    output_tokens=int(row.output_tokens or 0),
                    cache_read_tokens=int(row.cache_read_tokens or 0),
                    cache_write_tokens=int(row.cache_write_tokens or 0),
                    reasoning_tokens=int(row.reasoning_tokens or 0),
                )
            )
        return [
            ModelUsageActivitySeries(provider=provider, model=model, days=days)
            for (provider, model), days in grouped.items()
        ]


model_usage_activity_storage = SQLiteModelUsageActivityStorage()

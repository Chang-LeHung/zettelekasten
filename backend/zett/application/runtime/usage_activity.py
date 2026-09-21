"""Application view of model usage activity for the settings page."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

from zett_agent import ModelUsageActivityStorage

from ...infra.persistence.dao import model_usage_activity_storage
from ..schemas import ModelUsageActivitySeriesOut, UsageActivityDayOut


class UsageActivityService:
    """Read and zero-fill daily model usage for a calendar window."""

    def __init__(self, storage: ModelUsageActivityStorage = model_usage_activity_storage) -> None:
        self._storage = storage

    async def get(self, days: int) -> list[UsageActivityDayOut]:
        """Return one entry per UTC day, including days without requests."""
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        rows = await self._storage.activity(start=start, end=today)
        by_date = {row.date: row for row in rows}
        return [
            UsageActivityDayOut(
                date=current,
                requests=row.requests if row is not None else 0,
                input_tokens=row.input_tokens if row is not None else 0,
                output_tokens=row.output_tokens if row is not None else 0,
                cache_read_tokens=row.cache_read_tokens if row is not None else 0,
                cache_write_tokens=row.cache_write_tokens if row is not None else 0,
                reasoning_tokens=row.reasoning_tokens if row is not None else 0,
                total_tokens=row.total_tokens if row is not None else 0,
            )
            for current in _dates(start, today)
            for row in (by_date.get(current),)
        ]

    async def get_by_model(self, days: int) -> list[ModelUsageActivitySeriesOut]:
        """Return zero-filled daily activity for each provider model pair."""
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        rows = await self._storage.model_activity(start=start, end=today)
        series: list[ModelUsageActivitySeriesOut] = []
        for row in rows:
            by_date = {day.date: day for day in row.days}
            daily = [
                UsageActivityDayOut(
                    date=current,
                    requests=day.requests if day is not None else 0,
                    input_tokens=day.input_tokens if day is not None else 0,
                    output_tokens=day.output_tokens if day is not None else 0,
                    cache_read_tokens=day.cache_read_tokens if day is not None else 0,
                    cache_write_tokens=day.cache_write_tokens if day is not None else 0,
                    reasoning_tokens=day.reasoning_tokens if day is not None else 0,
                    total_tokens=day.total_tokens if day is not None else 0,
                )
                for current in _dates(start, today)
                for day in (by_date.get(current),)
            ]
            series.append(
                ModelUsageActivitySeriesOut(
                    provider=row.provider,
                    model=row.model,
                    days=daily,
                )
            )
        return sorted(
            series,
            key=lambda item: sum(day.total_tokens for day in item.days),
            reverse=True,
        )


def _dates(start: date, end: date) -> Iterator[date]:
    """Yield every inclusive UTC date in order."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


usage_activity_service = UsageActivityService()

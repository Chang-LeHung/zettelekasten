"""Application view of model usage activity for the settings page."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

from zett_agent import ModelUsageActivityStorage

from ..infra.dao import model_usage_activity_storage
from .schemas import UsageActivityDayOut


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


def _dates(start: date, end: date) -> Iterator[date]:
    """Yield every inclusive UTC date in order."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


usage_activity_service = UsageActivityService()

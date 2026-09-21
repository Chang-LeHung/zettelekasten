"""Cron schedule validation and next-occurrence calculation."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from ...schemas import CronSchedule


def validate_schedule(schedule: CronSchedule) -> ZoneInfo:
    """Validate a Cron expression and resolve its IANA time zone."""
    if not croniter.is_valid(schedule.expression):
        raise ValueError(f"Invalid cron expression: {schedule.expression}")
    try:
        return ZoneInfo(schedule.timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown timezone: {schedule.timezone}") from error


def next_run_after(schedule: CronSchedule, after: datetime) -> datetime:
    """Return the next Cron occurrence strictly after ``after`` in UTC."""
    timezone = validate_schedule(schedule)
    normalized_after = after.replace(tzinfo=UTC) if after.tzinfo is None else after.astimezone(UTC)
    local_after = normalized_after.astimezone(timezone)
    next_local = croniter(schedule.expression, local_after).get_next(datetime)
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=timezone)
    return next_local.astimezone(UTC)


__all__ = ["next_run_after", "validate_schedule"]

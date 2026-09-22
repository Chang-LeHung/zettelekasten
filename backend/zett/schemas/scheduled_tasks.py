"""Typed models for persistent background scheduled tasks."""

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import JsonValue


class ScheduledTaskRunStatus(StrEnum):
    """Lifecycle state of one scheduled or manually requested execution.

    State transitions::

        Submission:

            manual request -------------------> [PENDING]
            due occurrence
                +-- task lease is busy ------> [SKIPPED]
                +-- queued ------------------> [PENDING]

        Execution:

            [PENDING] --worker claim---------> [RUNNING]
                |
                +-- task missing or busy ---> [SKIPPED]

            [RUNNING] --success--------------> [SUCCEEDED]
                      --error or timeout-----> [FAILED]
                      --worker cancelled-----> [CANCELLED]
                      --lease expired--------> [INTERRUPTED]
                      --executor skipped-----> [SKIPPED]

        Terminal states are SUCCEEDED, FAILED, SKIPPED, CANCELLED, and
        INTERRUPTED. PENDING is the durable queue entry written by either a
        manual request or the scheduler. A scheduled occurrence that cannot
        start because its task is busy is inserted directly as SKIPPED.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ScheduledTaskTrigger(StrEnum):
    """How one scheduled task run was requested."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"


class ScheduledTaskOverlapPolicy(StrEnum):
    """How an occurrence behaves while the same task still has a live lease."""

    SKIP = "skip"


class CronSchedule(BaseModel):
    """Five- or six-field Cron expression evaluated in one IANA time zone."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expression: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)

    @field_validator("expression", "timezone")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Cron schedule values cannot be blank")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Reject values that are not resolvable IANA time zones."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {value}") from error
        return value


class ScheduledTaskAction(BaseModel):
    """Opaque action selected and validated by the scheduler executor registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ScheduledTaskCreate(BaseModel):
    """User-supplied fields used to create or replace one scheduled task."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    schedule: CronSchedule
    action: ScheduledTaskAction
    enabled: bool = True
    timeout_seconds: int = Field(default=600, ge=1, le=86_400)
    overlap_policy: ScheduledTaskOverlapPolicy = ScheduledTaskOverlapPolicy.SKIP

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Task name cannot be blank")
        return normalized


class ScheduledTaskWrite(BaseModel):
    """Complete mutable scheduled-task fields accepted by storage."""

    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool
    schedule: CronSchedule
    action: ScheduledTaskAction
    next_run_at: datetime
    timeout_seconds: int
    overlap_policy: ScheduledTaskOverlapPolicy


class ScheduledTaskEntity(BaseModel):
    """One persisted scheduled task with its current lease state."""

    id: str
    name: str
    enabled: bool
    schedule: CronSchedule
    action: ScheduledTaskAction
    next_run_at: datetime
    timeout_seconds: int
    overlap_policy: ScheduledTaskOverlapPolicy
    lease_run_id: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScheduledTaskRunCreate(BaseModel):
    """Complete fields required to append one scheduled-task run."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=36)
    task_id: str
    scheduled_for: datetime
    trigger_kind: ScheduledTaskTrigger
    status: ScheduledTaskRunStatus
    idempotency_key: str
    action: ScheduledTaskAction
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output: dict[str, JsonValue] | None = None
    error_type: str | None = None
    error_message: str | None = None


class ScheduledTaskRunEntity(BaseModel):
    """One persisted scheduled-task execution record."""

    id: str
    task_id: str
    scheduled_for: datetime
    trigger_kind: ScheduledTaskTrigger
    status: ScheduledTaskRunStatus
    idempotency_key: str
    action: ScheduledTaskAction
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output: dict[str, JsonValue] | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ScheduledTaskListOptions(BaseModel):
    """Filtering and pagination for scheduled-task definitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ScheduledTaskRunListOptions(BaseModel):
    """Filtering and pagination for scheduled-task execution history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str | None = None
    statuses: tuple[ScheduledTaskRunStatus, ...] = ()
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

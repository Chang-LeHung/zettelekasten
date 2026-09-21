"""Persistence models for background scheduled tasks and their run history.

``scheduled_tasks`` stores the durable task definition and the current lease
that prevents overlapping execution. ``scheduled_task_runs`` stores each
scheduled or manually requested execution and its terminal result.

Indexes stay on independent columns used by the scheduler queries:

* task ``next_run_at`` finds due work;
* task ``lease_expires_at`` finds abandoned runs;
* run ``task_id`` pages one task's history;
* run ``status`` finds queued runs;
* run ``idempotency_key`` prevents one occurrence from being inserted twice.
"""

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScheduledTaskRow(Base):
    """One task definition and its current execution lease.

    Example:
        ``"每日学习总结"`` runs at 09:00 Asia/Shanghai. Its ``next_run_at`` is
        stored as UTC, while ``action_payload_json`` names the Provider and
        prompt. When the scheduler queues an occurrence, it writes
        ``lease_run_id`` and ``lease_expires_at``. A worker later claims the
        pending run; other workers treat the task as busy until the lease
        expires or the owning run finishes.
    """

    __tablename__ = "scheduled_tasks"

    # UUIDv7 identity, for example "019970ca-...". This is the ID returned by
    # the task API and referenced by every scheduled_task_runs row.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # User-facing task name, for example "每日学习总结". It is also used as the
    # initial title when an agent_prompt run creates a new Session.
    name: Mapped[str] = mapped_column(String(200))

    # Whether due occurrences may be claimed. Disabling a task does not delete
    # its definition or history; enabling it recomputes next_run_at from now.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # JSON encoding of CronSchedule. Example:
    # {"expression": "0 9 * * *", "timezone": "Asia/Shanghai"}.
    # The expression is interpreted in the named IANA time zone.
    schedule_json: Mapped[str] = mapped_column(Text)

    # Executor discriminator, for example "agent_prompt". The scheduler copies
    # it into the run; the worker uses it to look up a registered ActionExecutor.
    action_kind: Mapped[str] = mapped_column(String(100))

    # Executor-owned JSON payload. Example for agent_prompt:
    # {"provider_id": "019970...", "message": "整理今天的学习内容",
    #  "reasoning_effort": "medium"}.
    action_payload_json: Mapped[str] = mapped_column(Text, default="{}")

    # Next scheduled occurrence as UTC. Example:
    # 2026-09-22T01:00:00Z for 09:00 Asia/Shanghai.
    # This is the scheduler's source of truth, not a value derived from memory.
    next_run_at: Mapped[datetime] = mapped_column(index=True)

    # Maximum executor runtime in seconds. Example: 600 means the worker cancels
    # the action after ten minutes and records a failed run.
    timeout_seconds: Mapped[int] = mapped_column(Integer)

    # Policy for an occurrence that arrives while the task is already running.
    # Current value: "skip"; a second run record is written with status
    # "skipped" instead of starting concurrent execution.
    overlap_policy: Mapped[str] = mapped_column(String(32))

    # ID of the scheduled_task_runs row currently owning this task. Example:
    # "019970cb-...". Null means the task is available to a worker. This is a
    # plain reference, not a database foreign key.
    lease_run_id: Mapped[str | None] = mapped_column(String(36))

    # UTC deadline for the current owner. A worker that crashes stops renewing
    # this value; recovery marks the referenced run interrupted once it expires.
    # Example: 2026-09-21T00:11:00Z for a ten-minute timeout plus a safety window.
    lease_expires_at: Mapped[datetime | None] = mapped_column(index=True)

    # UTC time when the definition row was created.
    created_at: Mapped[datetime] = mapped_column()

    # UTC time when editable task fields, the next occurrence, or the lease were
    # last changed.
    updated_at: Mapped[datetime] = mapped_column()


class ScheduledTaskRunRow(Base):
    """One execution record for a scheduled task.

    Example:
        At ``2026-09-22T01:00:00Z`` the scheduler creates a row with trigger
        ``"scheduled"`` and status ``"pending"``. A worker changes it to
        ``"running"``, and after the action returns writes ``"succeeded"`` plus
        an ``output_json`` such as ``{"session_id": "019970..."}``. The row is
        not deleted when the task is updated because it keeps the action
        snapshot that actually ran.
    """

    __tablename__ = "scheduled_task_runs"

    # UUIDv7 identity for this execution. Also used as request_id for an
    # agent_prompt run, for example "019970cb-...".
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Owning scheduled_tasks.id. This is the independent index used to page one
    # task's history; no database foreign key is declared.
    task_id: Mapped[str] = mapped_column(String(36), index=True)

    # The occurrence time that caused this run, stored as UTC. A manual run uses
    # the request time. Example: 2026-09-22T01:00:00Z.
    scheduled_for: Mapped[datetime] = mapped_column()

    # "scheduled" when due time claimed the run, or "manual" for run-now.
    trigger_kind: Mapped[str] = mapped_column(String(32))

    # Current lifecycle state. Values: pending, running, succeeded, failed,
    # skipped, cancelled, interrupted. Scheduler-created and manual runs both
    # start as pending; only the worker claim transitions them to running.
    status: Mapped[str] = mapped_column(String(32), index=True)

    # Unique deduplication key. Scheduled example:
    # "scheduled:<task-id>:2026-09-22T01:00:00+00:00"; manual example:
    # "manual:<run-id>". A unique index prevents duplicate occurrence creation.
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Action type copied when the run starts. It allows history to remain clear
    # even if the task definition changes later. Example: "agent_prompt".
    action_kind: Mapped[str] = mapped_column(String(100))

    # Action payload snapshot used by this run. Example:
    # {"provider_id": "019970...", "message": "生成今日总结"}.
    action_payload_json: Mapped[str] = mapped_column(Text, default="{}")

    # UTC time when a worker claimed the run. Null while it is pending.
    started_at: Mapped[datetime | None] = mapped_column()

    # UTC time when the run reached a terminal status. Null while pending/running.
    completed_at: Mapped[datetime | None] = mapped_column()

    # JSON output returned by the executor. Example for agent_prompt:
    # {"session_id": "019970...", "model": "gpt-5",
    #  "content_preview": "今天的学习总结..."}.
    output_json: Mapped[str | None] = mapped_column(Text)

    # Exception class for failed, interrupted, or cancelled runs. Example:
    # "TimeoutError", "LeaseExpired", or "ProviderResponseError".
    error_type: Mapped[str | None] = mapped_column(String(255))

    # Human-readable failure or skip reason. Example:
    # "Scheduled task already has a running occurrence".
    error_message: Mapped[str | None] = mapped_column(Text)

    # UTC time when this execution record was created.
    created_at: Mapped[datetime] = mapped_column()

    # UTC time when status, output, or error fields were last changed.
    updated_at: Mapped[datetime] = mapped_column()

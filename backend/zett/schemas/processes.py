"""Typed heartbeat and health models for background Zett processes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .._compat import StrEnum


class ProcessRole(StrEnum):
    """Long-running process roles supervised by the Web service."""

    SCHEDULER = "scheduler"
    WORKER = "worker"


class ProcessHeartbeatStatus(StrEnum):
    """Lifecycle state reported by one long-running process."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"


class ProcessHeartbeatIn(BaseModel):
    """Mutable heartbeat fields written by one process instance."""

    model_config = ConfigDict(extra="forbid")

    role: ProcessRole
    instance_id: str = Field(min_length=1, max_length=64)
    pid: int = Field(ge=1)
    status: ProcessHeartbeatStatus
    metadata: dict[str, str] = Field(default_factory=dict)


class ProcessHeartbeatRecord(BaseModel):
    """One in-memory process heartbeat."""

    role: ProcessRole
    instance_id: str
    pid: int
    status: ProcessHeartbeatStatus
    metadata: dict[str, str] = Field(default_factory=dict)
    started_at: datetime
    heartbeat_at: datetime
    stopped_at: datetime | None = None


class ProcessInstanceHealth(BaseModel):
    """Freshness of one process instance."""

    instance_id: str
    pid: int
    status: ProcessHeartbeatStatus
    heartbeat_at: datetime
    age_seconds: float


class ProcessRoleHealth(BaseModel):
    """Aggregated health for one required process role."""

    role: ProcessRole
    healthy: bool
    active_processes: int
    required_processes: int
    stale_after_seconds: float
    instances: list[ProcessInstanceHealth] = Field(default_factory=list)


class ProcessHealthReport(BaseModel):
    """Overall health of scheduler and worker processes."""

    healthy: bool
    checked_at: datetime
    roles: list[ProcessRoleHealth]


class ServerRuntimeState(BaseModel):
    """Best-effort process state persisted for ``zett stop`` and restart checks."""

    model_config = ConfigDict(extra="ignore")

    server_pid: int | None = Field(default=None, ge=1)
    port: int | None = Field(default=None, ge=1, le=65_535)
    scheduler_pids: list[int] = Field(default_factory=list)
    worker_pids: list[int] = Field(default_factory=list)
    started_at: datetime | None = None

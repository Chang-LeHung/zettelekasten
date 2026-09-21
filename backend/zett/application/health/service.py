"""Health projection for scheduler and worker heartbeat records."""

from collections.abc import Callable
from datetime import UTC, datetime

from ...config import settings
from ...schemas import (
    ProcessHealthReport,
    ProcessHeartbeatRecord,
    ProcessHeartbeatStatus,
    ProcessInstanceHealth,
    ProcessRole,
    ProcessRoleHealth,
)
from .registry import ProcessHeartbeatRegistry, process_heartbeat_registry


def _normalize(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ProcessHealthService:
    """Project in-memory heartbeats into API-safe health reports."""

    def __init__(
        self,
        *,
        registry: ProcessHeartbeatRegistry | None = None,
        required_workers: int = settings.worker_processes,
        heartbeat_timeout_seconds: float = settings.heartbeat_timeout_seconds,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.registry = registry or process_heartbeat_registry
        self.required_workers = max(1, required_workers)
        self.heartbeat_timeout_seconds = max(0.1, heartbeat_timeout_seconds)
        self.clock = clock

    async def report(self) -> ProcessHealthReport:
        now = _normalize(self.clock())
        heartbeats = await self.registry.list_all()
        roles = [
            self._role_health(role=ProcessRole.SCHEDULER, required=1, heartbeats=heartbeats, now=now),
            self._role_health(
                role=ProcessRole.WORKER,
                required=self.required_workers,
                heartbeats=heartbeats,
                now=now,
            ),
        ]
        return ProcessHealthReport(
            healthy=all(role.healthy for role in roles),
            checked_at=now,
            roles=roles,
        )

    def _role_health(
        self,
        *,
        role: ProcessRole,
        required: int,
        heartbeats: list[ProcessHeartbeatRecord],
        now: datetime,
    ) -> ProcessRoleHealth:
        instances = []
        for heartbeat in heartbeats:
            if heartbeat.role is not role or heartbeat.status is ProcessHeartbeatStatus.STOPPED:
                continue
            age = max(0.0, (now - heartbeat.heartbeat_at).total_seconds())
            instances.append(
                ProcessInstanceHealth(
                    instance_id=heartbeat.instance_id,
                    pid=heartbeat.pid,
                    status=heartbeat.status,
                    heartbeat_at=heartbeat.heartbeat_at,
                    age_seconds=age,
                )
            )
        active = sum(instance.age_seconds <= self.heartbeat_timeout_seconds for instance in instances)
        return ProcessRoleHealth(
            role=role,
            healthy=active >= required,
            active_processes=active,
            required_processes=required,
            stale_after_seconds=self.heartbeat_timeout_seconds,
            instances=instances,
        )


process_health_service = ProcessHealthService(registry=process_heartbeat_registry)

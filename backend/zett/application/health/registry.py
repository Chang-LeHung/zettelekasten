"""In-memory heartbeat registry owned by the FastAPI process."""

from __future__ import annotations

import asyncio
from datetime import datetime

from ..._compat import UTC
from ...schemas import (
    ProcessHeartbeatIn,
    ProcessHeartbeatRecord,
    ProcessHeartbeatStatus,
    ProcessRole,
)


def _normalize(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ProcessHeartbeatRegistry:
    """Keep the latest heartbeat for every process in FastAPI memory."""

    def __init__(self) -> None:
        self._records: dict[str, ProcessHeartbeatRecord] = {}
        self._lock = asyncio.Lock()

    async def record(
        self,
        heartbeat: ProcessHeartbeatIn,
        *,
        now: datetime | None = None,
    ) -> ProcessHeartbeatRecord:
        """Create or refresh one in-memory heartbeat."""
        current = _normalize(now or datetime.now(UTC))
        async with self._lock:
            previous = self._records.get(heartbeat.instance_id)
            if previous is not None and previous.role is not heartbeat.role:
                raise ValueError("A heartbeat instance cannot change process role")
            started_at = previous.started_at if previous is not None else current
            record = ProcessHeartbeatRecord(
                role=heartbeat.role,
                instance_id=heartbeat.instance_id,
                pid=heartbeat.pid,
                status=heartbeat.status,
                metadata=heartbeat.metadata,
                started_at=started_at,
                heartbeat_at=current,
                stopped_at=current if heartbeat.status is ProcessHeartbeatStatus.STOPPED else None,
            )
            self._records[heartbeat.instance_id] = record
            return record

    async def get(self, instance_id: str) -> ProcessHeartbeatRecord | None:
        async with self._lock:
            return self._records.get(instance_id)

    async def list_all(self) -> list[ProcessHeartbeatRecord]:
        async with self._lock:
            return sorted(self._records.values(), key=lambda item: (item.started_at, item.instance_id))

    async def list_fresh(self, *, role: ProcessRole, stale_before: datetime) -> list[ProcessHeartbeatRecord]:
        cutoff = _normalize(stale_before)
        async with self._lock:
            return sorted(
                (
                    heartbeat
                    for heartbeat in self._records.values()
                    if heartbeat.role is role
                    and heartbeat.status is not ProcessHeartbeatStatus.STOPPED
                    and heartbeat.heartbeat_at >= cutoff
                ),
                key=lambda item: (item.started_at, item.instance_id),
            )

    async def clear(self) -> None:
        """Clear all heartbeat state, primarily for process/test isolation."""
        async with self._lock:
            self._records.clear()


process_heartbeat_registry = ProcessHeartbeatRegistry()

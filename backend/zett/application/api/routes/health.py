"""Health endpoints for supervised background processes."""

from fastapi import APIRouter, status

from ....schemas import ProcessHealthReport, ProcessHeartbeatIn, ProcessHeartbeatRecord
from ...health import process_health_service, process_heartbeat_registry

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/processes", response_model=ProcessHealthReport)
async def process_health() -> ProcessHealthReport:
    """Report whether scheduler and worker heartbeat requirements are met."""
    return await process_health_service.report()


@router.post(
    "/processes/heartbeat",
    response_model=ProcessHeartbeatRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
async def report_process_heartbeat(payload: ProcessHeartbeatIn) -> ProcessHeartbeatRecord:
    """Receive one in-memory scheduler or worker heartbeat."""
    return await process_heartbeat_registry.record(payload)

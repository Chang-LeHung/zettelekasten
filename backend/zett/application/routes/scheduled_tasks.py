"""HTTP control plane for independently scheduled background tasks."""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ...schemas import (
    AGENT_PROMPT_ACTION_KIND,
    AgentPromptAction,
    ScheduledTaskCreate,
    ScheduledTaskEntity,
    ScheduledTaskListOptions,
    ScheduledTaskRunEntity,
    ScheduledTaskRunListOptions,
    ScheduledTaskRunStatus,
)
from ..scheduled_tasks import scheduled_task_service

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


class ScheduledTaskEnabledIn(BaseModel):
    """Enable or disable one task without replacing its complete definition."""

    enabled: bool


def _validate_action(payload: ScheduledTaskCreate) -> ScheduledTaskCreate:
    if payload.action.kind != AGENT_PROMPT_ACTION_KIND:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unsupported scheduled action: {payload.action.kind}",
        )
    try:
        AgentPromptAction.model_validate(payload.action.payload)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return payload


@router.get("", response_model=list[ScheduledTaskEntity])
async def list_scheduled_tasks(
    enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ScheduledTaskEntity]:
    """List persisted scheduled-task definitions."""
    return await scheduled_task_service.list(ScheduledTaskListOptions(enabled=enabled, limit=limit, offset=offset))


@router.post("", response_model=ScheduledTaskEntity, status_code=status.HTTP_201_CREATED)
async def create_scheduled_task(payload: ScheduledTaskCreate) -> ScheduledTaskEntity:
    """Validate a Cron definition and persist it for the scheduler worker."""
    try:
        return await scheduled_task_service.create(_validate_action(payload))
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/{task_id}", response_model=ScheduledTaskEntity)
async def get_scheduled_task(task_id: str) -> ScheduledTaskEntity:
    """Return one scheduled-task definition."""
    task = await scheduled_task_service.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheduled task not found")
    return task


@router.put("/{task_id}", response_model=ScheduledTaskEntity)
async def update_scheduled_task(task_id: str, payload: ScheduledTaskCreate) -> ScheduledTaskEntity:
    """Replace one task definition and recompute its next occurrence."""
    try:
        return await scheduled_task_service.update(task_id, _validate_action(payload))
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.patch("/{task_id}/enabled", response_model=ScheduledTaskEntity)
async def set_scheduled_task_enabled(
    task_id: str,
    payload: ScheduledTaskEnabledIn,
) -> ScheduledTaskEntity:
    """Enable or disable one task without changing its action definition."""
    try:
        return await scheduled_task_service.set_enabled(task_id, payload.enabled)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


@router.post("/{task_id}/run", response_model=ScheduledTaskRunEntity, status_code=status.HTTP_202_ACCEPTED)
async def run_scheduled_task_now(task_id: str) -> ScheduledTaskRunEntity:
    """Queue one manual occurrence for the independent scheduler process."""
    try:
        return await scheduled_task_service.run_now(task_id)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


@router.get("/{task_id}/runs", response_model=list[ScheduledTaskRunEntity])
async def list_scheduled_task_runs(
    task_id: str,
    run_status: list[ScheduledTaskRunStatus] = Query(default=[]),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ScheduledTaskRunEntity]:
    """Return one task's execution history in reverse creation order."""
    if await scheduled_task_service.get(task_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheduled task not found")
    return await scheduled_task_service.list_runs(
        ScheduledTaskRunListOptions(
            task_id=task_id,
            statuses=tuple(run_status),
            limit=limit,
            offset=offset,
        )
    )


@router.delete("/{task_id}", response_model=dict[str, bool])
async def delete_scheduled_task(task_id: str) -> dict[str, bool]:
    """Delete a task and its explicit run history."""
    try:
        return {"ok": await scheduled_task_service.delete(task_id)}
    except ValueError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

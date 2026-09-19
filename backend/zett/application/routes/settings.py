"""Asynchronous endpoints for user-configurable runtime settings."""

from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import UsageActivityDayOut
from ..settings import RuntimeSettings, runtime_settings_service
from ..usage_activity import usage_activity_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=RuntimeSettings)
async def get_runtime_settings() -> RuntimeSettings:
    """Return persisted runtime settings with defaults applied."""
    return await runtime_settings_service.get()


@router.put("", response_model=RuntimeSettings)
async def update_runtime_settings(payload: RuntimeSettings) -> RuntimeSettings:
    """Replace the complete runtime settings document and increment its version."""
    return await runtime_settings_service.update(payload)


@router.get("/usage-activity", response_model=list[UsageActivityDayOut])
async def get_usage_activity(
    days: Annotated[int, Query(ge=1, le=366)] = 365,
) -> list[UsageActivityDayOut]:
    """Return daily model request and token activity for the settings chart."""
    return await usage_activity_service.get(days)

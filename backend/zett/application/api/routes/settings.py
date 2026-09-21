"""Asynchronous endpoints for user-configurable runtime settings."""

from typing import Annotated

from fastapi import APIRouter, Query

from ...runtime.settings import RuntimeSettings, runtime_settings_service
from ...runtime.usage_activity import usage_activity_service
from ..schemas import ModelUsageActivitySeriesOut, UsageActivityDayOut

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


@router.get("/model-usage-activity", response_model=list[ModelUsageActivitySeriesOut])
async def get_model_usage_activity(
    days: Annotated[int, Query(ge=1, le=366)] = 365,
) -> list[ModelUsageActivitySeriesOut]:
    """Return daily request and token activity grouped by provider model."""
    return await usage_activity_service.get_by_model(days)

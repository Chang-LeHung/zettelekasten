"""Asynchronous endpoints for user-configurable runtime settings."""

from fastapi import APIRouter

from ..dependencies import run_sync
from ..settings import RuntimeSettings, runtime_settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=RuntimeSettings)
async def get_runtime_settings() -> RuntimeSettings:
    """Return persisted runtime settings with defaults applied."""
    return await run_sync(runtime_settings_service.get)


@router.put("", response_model=RuntimeSettings)
async def update_runtime_settings(payload: RuntimeSettings) -> RuntimeSettings:
    """Replace the complete runtime settings document and increment its version."""
    return await run_sync(runtime_settings_service.update, payload)

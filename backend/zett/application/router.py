"""Aggregate application routers before the packaged frontend catch-all mount."""

from fastapi import APIRouter

from .routes.agent import router as agent_router
from .routes.artifacts import router as artifact_router
from .routes.assets import router as asset_router
from .routes.files import router as file_router
from .routes.health import router as health_router
from .routes.providers import router as provider_router
from .routes.scheduled_tasks import router as scheduled_task_router
from .routes.sessions import router as session_router
from .routes.settings import router as settings_router
from .routes.static_assets import router as static_asset_router
from .routes.tags import router as tag_router

api_router = APIRouter(prefix="/api")
api_router.include_router(session_router)
api_router.include_router(file_router)
api_router.include_router(health_router)
api_router.include_router(asset_router)
api_router.include_router(static_asset_router)
api_router.include_router(artifact_router)
api_router.include_router(provider_router)
api_router.include_router(scheduled_task_router)
api_router.include_router(agent_router)
api_router.include_router(settings_router)
api_router.include_router(tag_router)

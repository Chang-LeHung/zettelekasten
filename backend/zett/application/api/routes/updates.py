"""Endpoints for checking PyPI and installing a newer release."""

from fastapi import APIRouter

from ....schemas import UpdateInstallResult, UpdateRestartResult, UpdateStatus
from ...runtime import RuntimeService
from ...runtime.updates import update_service
from ..schemas import UpdateInstallIn

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("", response_model=UpdateStatus)
async def get_update_status(refresh: bool = False) -> UpdateStatus:
    """Report the newest release on PyPI and whether this copy can install it."""
    return await update_service.status(refresh=refresh)


@router.post("/install", response_model=UpdateInstallResult)
async def install_update(payload: UpdateInstallIn) -> UpdateInstallResult:
    """Hand one release to the installer that owns this copy.

    The answer reports the installer's own exit status: a checkout, a release
    that is no longer the newest, or a failed command all come back as
    ``ok=false`` with the reason, because the sidebar shows it as written.
    """
    return await update_service.install(payload.version)


@router.post("/restart", response_model=UpdateRestartResult)
async def restart_server() -> UpdateRestartResult:
    """Restart this server so an installed release replaces the running code.

    The answer only says a detached helper was started: that helper stops this
    process, so the client polls ``GET /api/updates`` until the new one answers.
    A server that ``zett start`` did not record is refused with the reason.
    """
    return await RuntimeService().request_restart()

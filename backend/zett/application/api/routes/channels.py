"""HTTP management endpoints for the in-process IM gateway package."""

from fastapi import APIRouter, HTTPException, Query, status

from ....infra.persistence.dao import provider_storage
from ....schemas import (
    Channel,
    ChannelLogin,
    ChannelLoginStart,
    ChannelUpdate,
)
from ...channels import channel_service

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[Channel])
async def list_channels() -> list[Channel]:
    """List configured channels."""
    return await channel_service.list_channels()


@router.put("/{channel_id}", response_model=Channel)
async def update_channel(channel_id: str, payload: ChannelUpdate) -> Channel:
    """Update one channel policy."""
    if payload.provider_id is not None and await provider_storage.resolve_connection(payload.provider_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enabled provider not found")
    try:
        return await channel_service.update_channel(channel_id, payload)
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.delete("/{channel_id}")
async def delete_channel(channel_id: str) -> dict[str, bool]:
    """Delete one channel and stop its connection."""
    return {"ok": await channel_service.delete_channel(channel_id)}


@router.post("/login/start", response_model=ChannelLogin, status_code=status.HTTP_201_CREATED)
async def start_channel_login(payload: ChannelLoginStart) -> ChannelLogin:
    """Create a QR login session and return it to the browser."""
    if await provider_storage.resolve_connection(payload.provider_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enabled provider not found")
    try:
        return await channel_service.start_login(payload)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/login/{login_id}", response_model=ChannelLogin)
async def get_channel_login(
    login_id: str,
    verify_code: str | None = Query(default=None, max_length=100),
) -> ChannelLogin:
    """Poll QR login and start the channel connection after the scan."""
    login = await channel_service.poll_login(login_id, verify_code=verify_code)
    if login is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel login session not found")
    return login


__all__ = ["router"]

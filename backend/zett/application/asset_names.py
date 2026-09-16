"""Application boundary for asset display names, independent of file paths."""

from typing import Annotated

from pydantic import BaseModel, StringConstraints

from ..infra.dao import session_asset_storage
from ..schemas import SessionAssetOut


class AssetRenameIn(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500, pattern=r"^[^\x00-\x1f\x7f]+$")
    ]


async def rename_asset(session_id: str, asset_id: str, payload: AssetRenameIn) -> SessionAssetOut:
    """Preserve immutable identity and references while changing a display name."""
    return await session_asset_storage.rename(session_id, asset_id, payload.name)

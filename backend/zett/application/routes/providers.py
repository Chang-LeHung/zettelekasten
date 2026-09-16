"""Asynchronous CRUD endpoints for encrypted model provider settings."""

from fastapi import APIRouter, HTTPException, Query, status

from ...infra.dao import provider_storage
from ...models import ProviderListOptions
from ...schemas import ProviderOut, ProviderWrite
from ..schemas import DeleteResponse, ProviderIn, ProviderResponse

router = APIRouter(prefix="/ai/providers", tags=["providers"])


def _response(provider: ProviderOut) -> ProviderResponse:
    temperature = provider.metadata.get("temperature")
    response = provider.metadata.get("response", False)
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        provider=provider.provider,
        model=provider.model,
        base_url=provider.base_url,
        api_key_configured=provider.api_key_configured,
        temperature=float(temperature) if isinstance(temperature, int | float) else None,
        response=response if isinstance(response, bool) else False,
        enabled=provider.enabled,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def _write(payload: ProviderIn, *, existing_id: str | None = None) -> ProviderWrite:
    api_key = payload.api_key
    if existing_id is not None and api_key is None:
        connection = await provider_storage.resolve_connection(existing_id, enabled_only=False)
        if connection is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
        if connection is not None and connection.api_key is not None:
            api_key = connection.api_key.get_secret_value()
    metadata: dict[str, object] = {}
    if payload.temperature is not None:
        metadata["temperature"] = payload.temperature
    metadata["response"] = payload.response
    return ProviderWrite(
        name=payload.name,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key=api_key,
        enabled=payload.enabled,
        metadata=metadata,
    )


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    q: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ProviderResponse]:
    """List safe provider metadata without credentials or ciphertext."""
    providers = await provider_storage.list(ProviderListOptions(query=q, enabled=enabled, limit=limit, offset=offset))
    return [_response(provider) for provider in providers]


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(payload: ProviderIn) -> ProviderResponse:
    """Encrypt and persist a model configuration."""
    return _response(await provider_storage.create(await _write(payload)))


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: str) -> ProviderResponse:
    """Read one safe provider configuration without decrypting its key."""
    provider = await provider_storage.get(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    return _response(provider)


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(provider_id: str, payload: ProviderIn) -> ProviderResponse:
    """Replace provider settings while a blank key preserves the stored key."""
    try:
        entity = await _write(payload, existing_id=provider_id)
        return _response(await provider_storage.update(provider_id, entity))
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found") from error


@router.delete("/{provider_id}", response_model=DeleteResponse)
async def delete_provider(provider_id: str) -> DeleteResponse:
    """Delete one local provider configuration."""
    return DeleteResponse(ok=await provider_storage.delete(provider_id))

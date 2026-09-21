"""Asynchronous CRUD endpoints for encrypted model provider settings."""

from fastapi import APIRouter, HTTPException, Query, status
from zett_agent import ProviderAuthError, ProviderResponseError

from ...infra.log import get_logger
from ...infra.persistence.dao import provider_storage
from ...schemas import ProviderConnection, ProviderEntity, ProviderListOptions, ProviderWrite
from ..provider_connections import ProviderConnectionTestError, verify_provider_connection
from ..schemas import DeleteResponse, ProviderDetailResponse, ProviderIn, ProviderResponse

router = APIRouter(prefix="/ai/providers", tags=["providers"])
logger = get_logger(__name__)


def _response(provider: ProviderEntity) -> ProviderResponse:
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


def _detail_response(provider: ProviderEntity, api_key: str | None) -> ProviderDetailResponse:
    """Add the decrypted credential only for the selected settings row."""
    return ProviderDetailResponse(**_response(provider).model_dump(), api_key=api_key)


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


async def _verify_provider(entity: ProviderWrite, provider_id: str) -> None:
    """Probe complete settings before create or update mutates storage."""
    connection = ProviderConnection(
        id=provider_id,
        provider=entity.provider,
        model=entity.model,
        base_url=entity.base_url,
        api_key=entity.api_key,
        metadata=entity.metadata,
    )
    try:
        await verify_provider_connection(connection)
    except ProviderAuthError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Provider rejected the API credential") from error
    except (ProviderConnectionTestError, ProviderResponseError, ValueError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Provider test timed out") from error
    except Exception as error:
        logger.exception("Provider connection test failed; provider_id=%s", provider_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Provider connection test failed") from error


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
    """Verify, encrypt, and persist a model configuration."""
    entity = await _write(payload)
    await _verify_provider(entity, "new-provider")
    return _response(await provider_storage.create(entity))


@router.get("/{provider_id}", response_model=ProviderDetailResponse)
async def get_provider(provider_id: str) -> ProviderDetailResponse:
    """Read one provider configuration and decrypt its key for local editing."""
    provider = await provider_storage.get(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    connection = await provider_storage.resolve_connection(provider_id, enabled_only=False)
    api_key = (
        connection.api_key.get_secret_value() if connection is not None and connection.api_key is not None else None
    )
    return _detail_response(provider, api_key)


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(provider_id: str, payload: ProviderIn) -> ProviderResponse:
    """Verify replacement settings while a blank key preserves the stored key."""
    try:
        entity = await _write(payload, existing_id=provider_id)
        await _verify_provider(entity, provider_id)
        return _response(await provider_storage.update(provider_id, entity))
    except KeyError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found") from error


@router.delete("/{provider_id}", response_model=DeleteResponse)
async def delete_provider(provider_id: str) -> DeleteResponse:
    """Delete one local provider configuration."""
    return DeleteResponse(ok=await provider_storage.delete(provider_id))

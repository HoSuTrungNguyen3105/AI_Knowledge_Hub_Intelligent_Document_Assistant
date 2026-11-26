from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.providers import (
    ModelCheckResult,
    ProviderCatalog,
    ProviderRateLimits,
    ProviderMetadata,
    ProviderModels,
    ProviderPatch,
    ProviderTestResult,
)
from app.services.ai.chat import ChatHTTP
from app.services.ai.http import ModelListingHTTP
from app.services.providers import ProviderService
from app.services.rate_limits import list_rate_limit_snapshots

router = APIRouter(prefix="/ai/providers", tags=["AI providers"])


def provider_http() -> ModelListingHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ModelListingHTTP()


ProviderHTTP = Annotated[ModelListingHTTP, Depends(provider_http)]


def provider_chat_http() -> ChatHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ChatHTTP()


ProviderChatHTTP = Annotated[ChatHTTP, Depends(provider_chat_http)]


@router.get("", response_model=ProviderCatalog)
async def list_providers(user: CurrentUser, db: Database, settings: AppSettings) -> ProviderCatalog:
    return await ProviderService(db, settings).catalog(user.id)


@router.get("/rate-limits", response_model=ProviderRateLimits)
async def list_rate_limits(user: CurrentUser, db: Database) -> ProviderRateLimits:
    snapshots = await list_rate_limit_snapshots(db, user.id)
    return ProviderRateLimits(snapshots=snapshots)


@router.patch("/{provider}", response_model=ProviderMetadata)
async def patch_provider(
    provider: str,
    patch: ProviderPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ProviderMetadata:
    return await ProviderService(db, settings).patch(user.id, provider, patch)


@router.post("/{provider}/test", response_model=ProviderTestResult)
async def test_provider(
    provider: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: ProviderHTTP,
) -> ProviderTestResult:
    return await ProviderService(db, settings, http).test(user.id, provider)


@router.get("/{provider}/models", response_model=ProviderModels)
async def provider_models(
    provider: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ProviderModels:
    return await ProviderService(db, settings).models(user.id, provider)


@router.post(
    "/{provider}/models/{model_id:path}/check", response_model=ModelCheckResult
)
async def check_model(
    provider: str,
    model_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    chat_http: ProviderChatHTTP,
) -> ModelCheckResult:
    service = ProviderService(db, settings, chat_http=chat_http)
    return await service.check_model(user.id, provider, model_id)


@router.delete("/{provider}", status_code=204)
async def delete_provider(
    provider: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> Response:
    await ProviderService(db, settings).delete(user.id, provider)
    return Response(status_code=204)
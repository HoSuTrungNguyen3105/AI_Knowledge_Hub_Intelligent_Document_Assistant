from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.providers import (
    ProviderCatalog,
    ProviderMetadata,
    ProviderModels,
    ProviderPatch,
    ProviderTestResult,
)
from app.services.ai.http import ModelListingHTTP
from app.services.providers import ProviderService

router = APIRouter(prefix="/ai/providers", tags=["AI providers"])


def provider_http() -> ModelListingHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ModelListingHTTP()


ProviderHTTP = Annotated[ModelListingHTTP, Depends(provider_http)]


@router.get("", response_model=ProviderCatalog)
def list_providers(user: CurrentUser, db: Database, settings: AppSettings) -> ProviderCatalog:
    return ProviderService(db, settings).catalog(user.id)


@router.patch("/{provider}", response_model=ProviderMetadata)
def patch_provider(
    provider: str,
    patch: ProviderPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ProviderMetadata:
    return ProviderService(db, settings).patch(user.id, provider, patch)


@router.post("/{provider}/test", response_model=ProviderTestResult)
def test_provider(
    provider: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: ProviderHTTP,
) -> ProviderTestResult:
    return ProviderService(db, settings, http).test(user.id, provider)


@router.get("/{provider}/models", response_model=ProviderModels)
def provider_models(
    provider: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ProviderModels:
    return ProviderService(db, settings).models(user.id, provider)


@router.delete("/{provider}", status_code=204)
def delete_provider(
    provider: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> Response:
    ProviderService(db, settings).delete(user.id, provider)
    return Response(status_code=204)

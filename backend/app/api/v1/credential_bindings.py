"""Credential binding endpoints.

Prefix: ``/ai/credential-bindings``. A binding maps a template
credential type to one of the user's own n8n credentials; installs and
the bulk re-apply endpoint then rewrite node credentials in workflow
JSON so one connected key serves every template that needs it.
"""

from fastapi import APIRouter, Depends
from typing import Annotated

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.n8n_platform import N8nApiHTTPDep
from app.schemas.credential_bindings import (
    ApplyInstalledOut,
    CredentialBindingOut,
    CredentialBindingSetIn,
    CredentialBindingsOut,
)
from app.services.credential_bindings import CredentialBindingService
from app.services.n8n_platform import N8nPlatformService

router = APIRouter(prefix="/ai/credential-bindings", tags=["credential-bindings"])


def _service(db: Database, settings: AppSettings, n8n_http) -> CredentialBindingService:
    return CredentialBindingService(db, N8nPlatformService(db, settings, n8n_http))


@router.get("", response_model=CredentialBindingsOut)
async def list_credential_bindings(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    n8n_http: N8nApiHTTPDep,
) -> CredentialBindingsOut:
    return await _service(db, settings, n8n_http).list_view(user.id)


@router.put("", response_model=CredentialBindingOut)
async def set_credential_binding(
    payload: CredentialBindingSetIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    n8n_http: N8nApiHTTPDep,
) -> CredentialBindingOut:
    return await _service(db, settings, n8n_http).set_binding(
        user.id, payload.cred_type, payload.n8n_credential_id
    )


@router.delete("/{cred_type}", status_code=204)
async def delete_credential_binding(
    cred_type: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    n8n_http: N8nApiHTTPDep,
) -> None:
    await _service(db, settings, n8n_http).delete_binding(user.id, cred_type)
    return None


@router.post("/apply-installed", response_model=ApplyInstalledOut)
async def apply_bindings_to_installed(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    n8n_http: N8nApiHTTPDep,
) -> ApplyInstalledOut:
    return await _service(db, settings, n8n_http).apply_to_installed(user.id)

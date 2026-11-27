from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.n8n_platform import n8n_api_http
from app.schemas.service_keys import (
    ServiceKeyCreateIn,
    ServiceKeyListOut,
    ServiceKeyOut,
    ServiceKeyPushOut,
    ServiceKeyUpdateIn,
    ServicePresetListOut,
)
from app.services.n8n_platform import N8nApiHTTP
from app.services.service_keys import PRESETS, ServiceKeysService

router = APIRouter(prefix="/ai/service-keys", tags=["service keys"])

# Shared with the n8n platform router so tests override ONE dependency
# and both surfaces talk to the same fake n8n.
N8nApiHTTPDep = Annotated[N8nApiHTTP, Depends(n8n_api_http)]


@router.get("/presets", response_model=ServicePresetListOut)
async def list_service_key_presets(user: CurrentUser) -> ServicePresetListOut:
    """The service presets and their fields — the single source the UI
    renders its forms from."""
    return ServicePresetListOut(items=list(PRESETS.values()))


@router.get("", response_model=ServiceKeyListOut)
async def list_service_keys(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> ServiceKeyListOut:
    """The user's vault entries. Values are never returned — only which
    fields have one."""
    items = await ServiceKeysService(db, settings, http).list(user.id)
    return ServiceKeyListOut(items=items, total=len(items))


@router.post("", response_model=ServiceKeyOut, status_code=201)
async def create_service_key(
    payload: ServiceKeyCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> ServiceKeyOut:
    """Store a new entry with every field value encrypted at rest."""
    return await ServiceKeysService(db, settings, http).create(user.id, payload)


@router.patch("/{key_id}", response_model=ServiceKeyOut)
async def update_service_key(
    key_id: str,
    payload: ServiceKeyUpdateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> ServiceKeyOut:
    """Partial update: omitted fields keep their stored value, an empty
    string clears a field."""
    return await ServiceKeysService(db, settings, http).update(user.id, key_id, payload)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_key(
    key_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> Response:
    """Delete the vault entry. The credential already pushed into n8n is
    NOT deleted — key rotation/removal in n8n stays a deliberate act."""
    await ServiceKeysService(db, settings, http).delete(user.id, key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{key_id}/push", response_model=ServiceKeyPushOut)
async def push_service_key(
    key_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> ServiceKeyPushOut:
    """Create or update the matching credential in the user's n8n.
    This is the "Update" button: MindFlow stays the source of truth and
    n8n receives the current values."""
    return await ServiceKeysService(db, settings, http).push(user.id, key_id)

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.resources import (
    ResourceCreate,
    ResourceList,
    ResourceOut,
    ResourcePatch,
)
from app.services.resources import ResourceService

router = APIRouter(tags=["Workforce"])


def webhook_transport() -> httpx.BaseTransport | None:
    """Outbound transport for the n8n agent.created webhook. None uses
    real HTTP; tests override this dependency with a MockTransport."""
    return None


WebhookTransportDep = Annotated[httpx.BaseTransport | None, Depends(webhook_transport)]


def _service(db, settings, transport=None) -> ResourceService:
    return ResourceService(db, settings, transport)


@router.get("/ai/resources", response_model=ResourceList)
async def list_resources(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    type: Literal["human", "ai"] | None = None,
) -> ResourceList:
    """The caller's workforce resources, optionally filtered by kind."""
    return await _service(db, settings).list(user.id, type)


@router.post("/ai/resources", response_model=ResourceOut, status_code=201)
async def create_resource(
    payload: ResourceCreate,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    transport: WebhookTransportDep,
) -> ResourceOut:
    """Create a resource. AI resources also fire the agent.created
    webhook to the caller's n8n; the delivery state is returned in
    n8n_sync and never fails the creation."""
    return await _service(db, settings, transport).create(user.id, payload)


@router.get("/ai/resources/{resource_id}", response_model=ResourceOut)
async def get_resource(
    resource_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ResourceOut:
    return await _service(db, settings).get(user.id, resource_id)


@router.patch("/ai/resources/{resource_id}", response_model=ResourceOut)
async def patch_resource(
    resource_id: UUID,
    payload: ResourcePatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ResourceOut:
    return await _service(db, settings).patch(user.id, resource_id, payload)


@router.delete("/ai/resources/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await _service(db, settings).delete(user.id, resource_id)
    return Response(status_code=204)


@router.post("/ai/resources/{resource_id}/sync-n8n", response_model=ResourceOut)
async def sync_resource_n8n(
    resource_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    transport: WebhookTransportDep,
) -> ResourceOut:
    """Re-send the agent.created webhook for an AI resource now."""
    return await _service(db, settings, transport).sync_now(user.id, resource_id)

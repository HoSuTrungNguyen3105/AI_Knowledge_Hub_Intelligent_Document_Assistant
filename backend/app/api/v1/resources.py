from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import CurrentUser, Database
from app.schemas.resources import (
    ResourceCreate,
    ResourceList,
    ResourceOut,
    ResourcePatch,
)
from app.services.resources import ResourceService

router = APIRouter(tags=["Workforce"])


def _service(db) -> ResourceService:
    return ResourceService(db)


@router.get("/ai/resources", response_model=ResourceList)
async def list_resources(
    user: CurrentUser, db: Database, type: Literal["human", "ai"] | None = None
) -> ResourceList:
    """The caller's workforce resources, optionally filtered by kind."""
    return await _service(db).list(user.id, type)


@router.post("/ai/resources", response_model=ResourceOut, status_code=201)
async def create_resource(
    payload: ResourceCreate, user: CurrentUser, db: Database
) -> ResourceOut:
    return await _service(db).create(user.id, payload)


@router.get("/ai/resources/{resource_id}", response_model=ResourceOut)
async def get_resource(
    resource_id: UUID, user: CurrentUser, db: Database
) -> ResourceOut:
    return await _service(db).get(user.id, resource_id)


@router.patch("/ai/resources/{resource_id}", response_model=ResourceOut)
async def patch_resource(
    resource_id: UUID, payload: ResourcePatch, user: CurrentUser, db: Database
) -> ResourceOut:
    return await _service(db).patch(user.id, resource_id, payload)


@router.delete("/ai/resources/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: UUID, user: CurrentUser, db: Database
) -> Response:
    await _service(db).delete(user.id, resource_id)
    return Response(status_code=204)

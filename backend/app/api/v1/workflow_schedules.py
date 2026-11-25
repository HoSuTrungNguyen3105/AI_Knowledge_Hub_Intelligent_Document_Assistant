from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import CurrentUser, Database
from app.schemas.workflow_schedules import (
    ScheduleCreate,
    ScheduleListOut,
    ScheduleNextRunsOut,
    ScheduleOut,
    SchedulePatch,
    SchedulePreviewIn,
    SchedulePreviewOut,
)
from app.services.workflow_schedules import WorkflowScheduleService

router = APIRouter(prefix="/ai/workflow-schedules", tags=["workflow schedules"])


def schedule_service(db: Database) -> WorkflowScheduleService:
    return WorkflowScheduleService(db)


Service = Annotated[WorkflowScheduleService, Depends(schedule_service)]


@router.get("", response_model=ScheduleListOut)
async def list_schedules(
    user: CurrentUser,
    service: Service,
    status: str | None = Query(default=None, pattern="^(active|paused|completed|error)$"),
    search: str | None = Query(default=None, max_length=200),
) -> ScheduleListOut:
    items, total, stats = await service.list(user.id, status=status, search=search)
    return ScheduleListOut(items=items, total=total, stats=stats)


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    payload: ScheduleCreate, user: CurrentUser, service: Service
) -> ScheduleOut:
    return await service.create(user.id, payload)


@router.post("/preview", response_model=SchedulePreviewOut)
async def preview_schedule(
    payload: SchedulePreviewIn, user: CurrentUser, service: Service
) -> SchedulePreviewOut:
    return service.preview(payload)


@router.get("/{schedule_id}", response_model=ScheduleOut)
async def get_schedule(
    schedule_id: UUID, user: CurrentUser, service: Service
) -> ScheduleOut:
    return await service.get(user.id, schedule_id)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: UUID,
    payload: SchedulePatch,
    user: CurrentUser,
    service: Service,
) -> ScheduleOut:
    return await service.update(user.id, schedule_id, payload)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: UUID, user: CurrentUser, service: Service
) -> Response:
    await service.delete(user.id, schedule_id)
    return Response(status_code=204)


@router.post("/{schedule_id}/pause", response_model=ScheduleOut)
async def pause_schedule(
    schedule_id: UUID, user: CurrentUser, service: Service
) -> ScheduleOut:
    return await service.pause(user.id, schedule_id)


@router.post("/{schedule_id}/resume", response_model=ScheduleOut)
async def resume_schedule(
    schedule_id: UUID, user: CurrentUser, service: Service
) -> ScheduleOut:
    return await service.resume(user.id, schedule_id)


@router.get("/{schedule_id}/next-runs", response_model=ScheduleNextRunsOut)
async def schedule_next_runs(
    schedule_id: UUID, user: CurrentUser, service: Service
) -> ScheduleNextRunsOut:
    return ScheduleNextRunsOut(
        next_runs=await service.next_runs(user.id, schedule_id)
    )

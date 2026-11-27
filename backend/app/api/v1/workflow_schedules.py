from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.n8n_factory import N8nHTTPDep
from app.api.v1.n8n_platform import N8nApiHTTPDep
from app.schemas.workflow_schedules import (
    ScheduleCreate,
    ScheduleExecutionListOut,
    ScheduleExecutionOut,
    ScheduleHealthOut,
    ScheduleListOut,
    ScheduleNextRunsOut,
    ScheduleOut,
    SchedulePatch,
    SchedulePreviewIn,
    SchedulePreviewOut,
    ScheduleTickOut,
)
from app.services.ai.base_provider import ProviderError
from app.services.n8n_platform import N8nPlatformService
from app.services.schedule_runner import ScheduleRunner
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


def schedule_runner(
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
    platform_http: N8nApiHTTPDep,
) -> ScheduleRunner:
    return ScheduleRunner(db, settings, http, platform_http)


Runner = Annotated[ScheduleRunner, Depends(schedule_runner)]


@router.post("/tick", response_model=ScheduleTickOut)
async def tick_schedules(
    runner: Runner,
    settings: AppSettings,
    x_scheduler_secret: str | None = Header(default=None),
) -> ScheduleTickOut:
    """Fire every due schedule. For external cron callers (which also
    keep the free-tier backend awake); guarded by a shared secret that
    never reaches the frontend."""
    if not settings.scheduler_tick_secret:
        raise ProviderError("scheduler_tick_disabled")
    if x_scheduler_secret != settings.scheduler_tick_secret:
        raise ProviderError("scheduler_tick_unauthorized")
    return await runner.tick(source="external")


@router.get("/health", response_model=ScheduleHealthOut)
async def schedule_health(
    user: CurrentUser,
    service: Service,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> ScheduleHealthOut:
    """Health of the firing chain for the Lịch chạy tab: whether the
    external tick is configured (boolean only — the secret itself never
    leaves the server), when the last tick was recorded, and whether
    n8n is currently reachable."""
    platform = N8nPlatformService(db, settings, http)
    return await service.health(settings, platform)


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


@router.post(
    "/{schedule_id}/run-now",
    response_model=ScheduleExecutionOut,
    status_code=202,
)
async def run_schedule_now(
    schedule_id: UUID, user: CurrentUser, runner: Runner
) -> ScheduleExecutionOut:
    """Fire the schedule immediately as a manual execution; the regular
    timetable (next_run_at) is left untouched."""
    return await runner.run_now(user.id, schedule_id)


@router.get(
    "/{schedule_id}/executions", response_model=ScheduleExecutionListOut
)
async def list_schedule_executions(
    schedule_id: UUID, user: CurrentUser, runner: Runner
) -> ScheduleExecutionListOut:
    items, total = await runner.list_executions(user.id, schedule_id)
    return ScheduleExecutionListOut(items=items, total=total)


@router.get("/{schedule_id}/next-runs", response_model=ScheduleNextRunsOut)
async def schedule_next_runs(
    schedule_id: UUID, user: CurrentUser, service: Service
) -> ScheduleNextRunsOut:
    return ScheduleNextRunsOut(
        next_runs=await service.next_runs(user.id, schedule_id)
    )

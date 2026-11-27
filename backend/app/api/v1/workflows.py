import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.workflows import (
    EventList,
    MessageList,
    PlanApplyIn,
    PlanApplyOut,
    PlanOut,
    PlanRequest,
    RoleCreate,
    RoleList,
    RoleOut,
    RolePatch,
    TaskList,
    TeamCreate,
    TeamList,
    TeamOut,
    TeamPatch,
    WorkflowCreate,
    WorkflowFileList,
    WorkflowList,
    WorkflowOut,
)
from app.services.ai.chat import ChatHTTP
from app.services.workflow_planning import PlanningService
from app.services.workflows import WorkflowService, launch_workflow

router = APIRouter(tags=["AI multi-agent"])

AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


def _service(db, settings, http) -> WorkflowService:
    return WorkflowService(db, settings, http)


# --- Role catalog --------------------------------------------------------------
@router.get("/ai/roles", response_model=RoleList)
async def list_roles(user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep):
    return await _service(db, settings, http).list_roles(user.id)


@router.post("/ai/roles", response_model=RoleOut, status_code=201)
async def create_role(
    payload: RoleCreate, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).create_role(user.id, payload)


@router.patch("/ai/roles/{slug}", response_model=RoleOut)
async def patch_role(
    slug: str,
    payload: RolePatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
):
    return await _service(db, settings, http).patch_role(user.id, slug, payload)


@router.delete("/ai/roles/{slug}", status_code=204)
async def delete_role(
    slug: str, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    await _service(db, settings, http).delete_role(user.id, slug)
    return Response(status_code=204)


# --- Teams -------------------------------------------------------------------
@router.get("/ai/agent-teams", response_model=TeamList)
async def list_teams(user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep):
    return await _service(db, settings, http).list_teams(user.id)


@router.post("/ai/agent-teams", response_model=TeamOut, status_code=201)
async def create_team(
    payload: TeamCreate, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).create_team(user.id, payload)


@router.get("/ai/agent-teams/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).get_team(user.id, team_id)


@router.patch("/ai/agent-teams/{team_id}", response_model=TeamOut)
async def patch_team(
    team_id: UUID,
    payload: TeamPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
):
    return await _service(db, settings, http).patch_team(user.id, team_id, payload)


@router.delete("/ai/agent-teams/{team_id}", status_code=204)
async def delete_team(
    team_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    await _service(db, settings, http).delete_team(user.id, team_id)
    return Response(status_code=204)


# --- Dynamic planning ----------------------------------------------------------
@router.post("/ai/agent-workflows/plan", response_model=PlanOut)
async def plan_workflow(
    payload: PlanRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
):
    """Task Analysis + Decomposition + Agent Selection: the Leader agent
    drafts a plan, the backend guarantees its shape (count in {1,2,3,5},
    cycle-free dependencies, lineup matched to real agents)."""
    return await PlanningService(db, settings, http).analyze(user.id, payload)


@router.post("/ai/agent-workflows/plan/apply", response_model=PlanApplyOut, status_code=201)
async def apply_workflow_plan(
    payload: PlanApplyIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
):
    """Materialize an approved plan: create the team from the lineup and
    a workflow carrying the plan, ready to start."""
    return await PlanningService(db, settings, http).apply(user.id, payload)


# --- Workflows -----------------------------------------------------------------
@router.get("/ai/agent-workflows", response_model=WorkflowList)
async def list_workflows(
    user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).list_workflows(user.id)


@router.post("/ai/agent-workflows", response_model=WorkflowOut, status_code=201)
async def create_workflow(
    payload: WorkflowCreate,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
):
    return await _service(db, settings, http).create_workflow(user.id, payload)


@router.get("/ai/agent-workflows/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).get_workflow(user.id, workflow_id)


@router.delete("/ai/agent-workflows/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    await _service(db, settings, http).delete_workflow(user.id, workflow_id)
    return Response(status_code=204)


async def _start(user, db, settings, http, workflow_id) -> WorkflowOut:
    service = _service(db, settings, http)
    claimed, owner = await service.prepare_start(user.id, workflow_id)
    launch_workflow(service, user.id, workflow_id, owner)
    return WorkflowService._workflow_out(claimed)


@router.post("/ai/agent-workflows/{workflow_id}/start", response_model=WorkflowOut)
async def start_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _start(user, db, settings, http, workflow_id)


@router.post("/ai/agent-workflows/{workflow_id}/resume", response_model=WorkflowOut)
async def resume_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _start(user, db, settings, http, workflow_id)


@router.post("/ai/agent-workflows/{workflow_id}/pause", response_model=WorkflowOut)
async def pause_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).pause_workflow(user.id, workflow_id)


@router.post("/ai/agent-workflows/{workflow_id}/cancel", response_model=WorkflowOut)
async def cancel_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).cancel_workflow(user.id, workflow_id)


@router.get("/ai/agent-workflows/{workflow_id}/files", response_model=WorkflowFileList)
async def list_files(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).list_files(user.id, workflow_id)


@router.get("/ai/agent-workflows/{workflow_id}/download.zip")
async def download_zip(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    filename, content = await _service(db, settings, http).build_download(user.id, workflow_id)
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/ai/agent-workflows/{workflow_id}/messages", response_model=MessageList)
async def list_messages(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).list_messages(user.id, workflow_id)


@router.get("/ai/agent-workflows/{workflow_id}/tasks", response_model=TaskList)
async def list_tasks(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).list_tasks(user.id, workflow_id)


@router.get("/ai/agent-workflows/{workflow_id}/events", response_model=EventList)
async def list_events(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    return await _service(db, settings, http).list_events(user.id, workflow_id)


@router.get("/ai/agent-workflows/{workflow_id}/stream")
async def stream_workflow(
    workflow_id: UUID, user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
):
    """Observe a workflow over SSE. Disconnecting never cancels the run."""
    service = _service(db, settings, http)
    await service.get_workflow(user.id, workflow_id)  # ownership check before stream opens

    async def generate() -> AsyncIterator[str]:
        seen: set[str] = set()
        while True:
            events = await service.list_events(user.id, workflow_id)
            for event in events.events:
                key = str(event.id)
                if key not in seen:
                    seen.add(key)
                    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: {event.event_type}\ndata: {data}\n\n"
            workflow = await service.get_workflow(user.id, workflow_id)
            if workflow.status in ("completed", "failed", "cancelled"):
                yield f"event: done\ndata: {json.dumps({'status': workflow.status})}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )

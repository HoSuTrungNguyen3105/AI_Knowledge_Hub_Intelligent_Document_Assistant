from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.allocations import (
    AllocationList,
    AllocationOut,
    DecideIn,
    ReassignIn,
    RecommendIn,
)
from app.schemas.projects import (
    AnalysisList,
    AnalysisOut,
    AnalyzeIn,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectPatch,
)
from app.services.ai.chat import ChatHTTP
from app.services.allocations import AllocationService
from app.services.projects import ProjectService

router = APIRouter(tags=["Workforce Projects"])

AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


def _service(db, settings, http=None) -> ProjectService:
    return ProjectService(db, settings, http)


@router.get("/ai/projects", response_model=ProjectList)
async def list_projects(user: CurrentUser, db: Database, settings: AppSettings) -> ProjectList:
    return await _service(db, settings).list(user.id)


@router.post("/ai/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate, user: CurrentUser, db: Database, settings: AppSettings
) -> ProjectOut:
    return await _service(db, settings).create(user.id, payload)


@router.get("/ai/projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ProjectOut:
    return await _service(db, settings).get(user.id, project_id)


@router.patch("/ai/projects/{project_id}", response_model=ProjectOut)
async def patch_project(
    project_id: UUID,
    payload: ProjectPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ProjectOut:
    return await _service(db, settings).patch(user.id, project_id, payload)


@router.delete("/ai/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await _service(db, settings).delete(user.id, project_id)
    return Response(status_code=204)


@router.get("/ai/projects/{project_id}/analyses", response_model=AnalysisList)
async def list_analyses(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> AnalysisList:
    return await _service(db, settings).list_analyses(user.id, project_id)


@router.post("/ai/projects/{project_id}/analyze", response_model=AnalysisOut)
async def analyze_project(
    project_id: UUID,
    payload: AnalyzeIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> AnalysisOut:
    """One LLM pass that breaks the project into assignable tasks. The
    model's JSON is validated before it is stored; an unreadable answer
    fails with analysis_invalid_response and stores nothing."""
    return await _service(db, settings, http).analyze(user.id, project_id, payload)


def _allocations(db, settings) -> AllocationService:
    return AllocationService(db, settings)


@router.post(
    "/ai/projects/{project_id}/recommend",
    response_model=AllocationOut,
    status_code=201,
)
async def recommend_team(
    project_id: UUID,
    payload: RecommendIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> AllocationOut:
    """Score every workforce resource against every task of an analysis
    (latest analysis unless analysis_id is given). Deterministic
    weighted scoring with hard-constraint exclusions — no LLM involved."""
    return await _allocations(db, settings).recommend(user.id, project_id, payload)


@router.get("/ai/projects/{project_id}/allocations", response_model=AllocationList)
async def list_allocations(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> AllocationList:
    return await _allocations(db, settings).list(user.id, project_id)


@router.get(
    "/ai/projects/{project_id}/allocations/{allocation_id}",
    response_model=AllocationOut,
)
async def get_allocation(
    project_id: UUID,
    allocation_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> AllocationOut:
    return await _allocations(db, settings).get(user.id, project_id, allocation_id)


@router.patch(
    "/ai/projects/{project_id}/allocations/{allocation_id}",
    response_model=AllocationOut,
)
async def reassign_allocation(
    project_id: UUID,
    allocation_id: UUID,
    payload: ReassignIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> AllocationOut:
    """Manager overrides picks before approval. Hard constraints still
    apply: an AI denied a task's scope cannot be assigned to it."""
    return await _allocations(db, settings).reassign(
        user.id, project_id, allocation_id, payload
    )


@router.post(
    "/ai/projects/{project_id}/allocations/{allocation_id}/decide",
    response_model=AllocationOut,
)
async def decide_allocation(
    project_id: UUID,
    allocation_id: UUID,
    payload: DecideIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> AllocationOut:
    """Approve (project moves to approved) or reject the proposed team."""
    return await _allocations(db, settings).decide(
        user.id, project_id, allocation_id, payload
    )

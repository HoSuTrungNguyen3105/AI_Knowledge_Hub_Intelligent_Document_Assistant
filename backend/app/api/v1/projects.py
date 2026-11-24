from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel

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
from app.services.ai.base_provider import ProviderError
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


class ProjectImportOut(BaseModel):
    project: ProjectOut
    analysis: AnalysisOut | None = None
    allocation: AllocationOut | None = None
    analysis_error: str | None = None


@router.post("/ai/projects/import", response_model=ProjectImportOut, status_code=201)
async def import_project(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
    file: UploadFile = File(...),
    name: str = Form(""),
    tech_stack: str = Form(""),
    provider: str = Form(...),
    model: str = Form(...),
) -> ProjectImportOut:
    """Upload a brief file (.md/.txt/.pdf/.docx): create the project
    from its text, then immediately analyze it and draft the team
    recommendation so the sections below fill in without extra clicks.
    A failed analysis keeps the created project and reports the error
    code in analysis_error instead of failing the whole upload."""
    service = _service(db, settings, http)
    data = await file.read()
    stack = [part.strip() for part in tech_stack.split(",") if part.strip()]
    project = await service.create_from_file(
        user.id,
        filename=file.filename or "brief",
        data=data,
        name=name,
        tech_stack=stack,
    )
    analysis = None
    allocation = None
    analysis_error = None
    try:
        analysis = await service.analyze(
            user.id, project.id, AnalyzeIn(provider=provider, model=model)
        )
        allocation = await _allocations(db, settings).recommend(
            user.id, project.id, RecommendIn()
        )
    except ProviderError as exc:
        analysis_error = exc.code
    # Re-read so the returned project carries its post-analysis status.
    project = await service.get(user.id, project.id)
    return ProjectImportOut(
        project=project,
        analysis=analysis,
        allocation=allocation,
        analysis_error=analysis_error,
    )


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

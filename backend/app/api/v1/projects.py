from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
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

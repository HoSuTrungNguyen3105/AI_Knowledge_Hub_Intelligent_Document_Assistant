from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.studio_projects import (
    ChangeList,
    FileContentOut,
    FileTreeOut,
    FileUpsertIn,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectPatch,
    RunCreateIn,
    RunListOut,
    RunOut,
)
from app.services.ai.chat import ChatHTTP
from app.services.studio_projects import StudioProjectService

router = APIRouter(tags=["Studio Projects"])

AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


def _service(db, settings, http=None) -> StudioProjectService:
    return StudioProjectService(db, settings, http)


@router.post("/ai/studio-projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate, user: CurrentUser, db: Database, settings: AppSettings
) -> ProjectOut:
    return await _service(db, settings).create_project(user.id, payload)


@router.post(
    "/ai/studio-projects/import-zip", response_model=ProjectOut, status_code=201
)
async def import_zip(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> ProjectOut:
    data = await file.read()
    return await _service(db, settings).import_zip(user.id, name, data)


@router.get("/ai/studio-projects", response_model=ProjectList)
async def list_projects(
    user: CurrentUser, db: Database, settings: AppSettings
) -> ProjectList:
    return await _service(db, settings).list_projects(user.id)


@router.get("/ai/studio-projects/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ProjectOut:
    return await _service(db, settings).get_project(user.id, project_id)


@router.patch("/ai/studio-projects/{project_id}", response_model=ProjectOut)
async def patch_project(
    project_id: UUID,
    payload: ProjectPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ProjectOut:
    return await _service(db, settings).patch_project(user.id, project_id, payload)


@router.delete("/ai/studio-projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
):
    await _service(db, settings).delete_project(user.id, project_id)
    return Response(status_code=204)


@router.get("/ai/studio-projects/{project_id}/files", response_model=FileTreeOut)
async def list_files(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> FileTreeOut:
    return await _service(db, settings).list_files(user.id, project_id)


@router.get(
    "/ai/studio-projects/{project_id}/file", response_model=FileContentOut
)
async def get_file(
    project_id: UUID,
    path: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> FileContentOut:
    return await _service(db, settings).get_file(user.id, project_id, path)


@router.put(
    "/ai/studio-projects/{project_id}/file", response_model=FileContentOut
)
async def upsert_file(
    project_id: UUID,
    path: str,
    payload: FileUpsertIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> FileContentOut:
    return await _service(db, settings).upsert_file(
        user.id, project_id, path, payload.content
    )


@router.delete("/ai/studio-projects/{project_id}/file", status_code=204)
async def delete_file(
    project_id: UUID,
    path: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
):
    await _service(db, settings).delete_file(user.id, project_id, path)
    return Response(status_code=204)


@router.get("/ai/studio-projects/{project_id}/export.zip")
async def export_zip(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    data, filename = await _service(db, settings).export_zip(user.id, project_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ai/studio-projects/{project_id}/changes", response_model=ChangeList)
async def list_changes(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ChangeList:
    return await _service(db, settings).list_changes(user.id, project_id)


@router.post(
    "/ai/studio-projects/{project_id}/runs",
    response_model=RunOut,
    status_code=201,
)
async def run_agents(
    project_id: UUID,
    payload: RunCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> RunOut:
    """Run the chosen Agents over the project's current files, in the
    given order, applying each Agent's edits before the next one reads."""
    return await _service(db, settings, http).run_agents(
        user.id, project_id, payload
    )


@router.get("/ai/studio-projects/{project_id}/runs", response_model=RunListOut)
async def list_runs(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunListOut:
    return await _service(db, settings).list_runs(user.id, project_id)

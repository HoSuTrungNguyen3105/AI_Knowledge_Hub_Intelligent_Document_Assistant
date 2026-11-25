"""Codebase Architecture Analyzer routes (PROJECT_SPEC.md).

Mounted under /api/v1/ai/code-analyzer; the spec's /api/code-analyzer
paths map onto the codebase's /api/v1/ai prefix like every other AI
module. The webhook callback is the one unauthenticated route: n8n
calls it with the shared x-mindflow-secret header instead of a user
session.
"""

from uuid import UUID

from fastapi import APIRouter, File, Header, UploadFile

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.code_analyzer import (
    CodeCallbackIn,
    CodeCallbackOut,
    CodeFileDetail,
    CodeProjectDetail,
    CodeProjectList,
    SeedDemoOut,
    UploadOut,
)
from app.services.code_analyzer import CodeAnalyzerService

router = APIRouter(prefix="/ai/code-analyzer", tags=["Code Analyzer"])


def _service(db, settings) -> CodeAnalyzerService:
    return CodeAnalyzerService(db, settings)


@router.get("/projects", response_model=CodeProjectList)
async def list_projects(user: CurrentUser, db: Database, settings: AppSettings):
    """The caller's own projects plus the public demo projects."""
    projects = await _service(db, settings).list_projects(user.id)
    return CodeProjectList(projects=projects)


@router.post("/seed-demo", response_model=SeedDemoOut)
async def seed_demo(user: CurrentUser, db: Database, settings: AppSettings):
    """Create the shared public demo project once (dev/demo only)."""
    return await _service(db, settings).seed_demo(user.id)


@router.post("/upload", response_model=UploadOut, status_code=201)
async def upload(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    file: UploadFile = File(...),
):
    """Ingest a ZIP: filter junk, statically parse imports, store the
    project, then hand file batches to the n8n analysis webhook."""
    data = await file.read()
    return await _service(db, settings).ingest_upload(
        user.id, file.filename or "codebase.zip", data
    )


@router.post("/webhook/callback", response_model=CodeCallbackOut)
async def webhook_callback(
    payload: CodeCallbackIn,
    db: Database,
    settings: AppSettings,
    x_mindflow_secret: str | None = Header(default=None),
):
    """Receive per-file AI results from the n8n analysis workflow."""
    return await _service(db, settings).apply_callback(x_mindflow_secret, payload)


@router.get("/projects/{project_id}", response_model=CodeProjectDetail)
async def get_project(
    project_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
):
    return await _service(db, settings).get_project(user.id, project_id)


@router.get(
    "/projects/{project_id}/files/{file_id}", response_model=CodeFileDetail
)
async def get_file(
    project_id: UUID,
    file_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
):
    return await _service(db, settings).get_file(user.id, project_id, file_id)
